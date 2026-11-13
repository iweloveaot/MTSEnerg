
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend/index.html"), "utf8");
const source = fs.readFileSync(path.join(root, "frontend/app.js"), "utf8");

function createElement(id) {
    return {
        id,
        hidden: false,
        disabled: false,
        value: "",
        textContent: "",
        children: [],
        handlers: {},
        appendChild(child) {
            this.children.push(child);
        },
        replaceChildren(...children) {
            this.children = children;
        },
        addEventListener(event, callback) {
            this.handlers[event] = callback;
        },
        focus() {},
    };
}

function createApp(responses = []) {
    const ids = [
        "chat-form", "message-input", "send-button",
        "chat-messages", "new-chat-button",
        "debug-toggle", "debug-details",
        "response-time", "source-documents",
        "application-status", "application-details",
        "application-offer",
        "accept-application-button",
        "decline-application-button",
        "load-history-button", "history-status", "history-list",
        "history-view-banner", "return-to-chat-button",
    ];

    const elements = Object.fromEntries(
        ids.map((id) => [id, createElement(id)])
    );

    elements["application-offer"].hidden = true;
    elements["application-details"].hidden = true;
    elements["history-list"].hidden = true;
    elements["history-view-banner"].hidden = true;

    const requests = [];

    const context = {
        document: {
            getElementById(id) {
                assert.ok(elements[id], `Неизвестный элемент: ${id}`);
                return elements[id];
            },
            createElement(tag) {
                return createElement(tag);
            },
        },
        crypto: {
            randomUUID: () => "test-session",
        },
        performance: {
            now: () => 100,
        },
        console,
        fetch: async (url, options) => {
            requests.push({ url, ...(options || {}) });
            const response = responses.shift();
            assert.ok(response, "Неожиданный запрос к API");
            return {
                ok: true,
                json: async () => response,
            };
        },
    };

    vm.runInNewContext(source, context);

    return { elements, requests };
}

async function submit(app, message) {
    const input = app.elements["message-input"];
    input.value = message;

    await app.elements["chat-form"].handlers.submit({
        preventDefault() {},
    });
}

async function click(app, id) {
    await app.elements[id].handlers.click();
    // Обработчик click не обязательно возвращает Promise.
    // Даём завершиться запущенному асинхронному запросу.
    await new Promise((resolve) => setImmediate(resolve));
}

test("HTML содержит обе кнопки", () => {
    assert.match(html, /id="application-offer"/);
    assert.match(html, /id="accept-application-button"/);
    assert.match(html, /id="decline-application-button"/);
});

test("Без сигнала backend кнопки скрыты", async () => {
    const app = createApp([
        { answer: "Здравствуйте", application: null },
    ]);

    await submit(app, "Привет");

    assert.equal(app.elements["application-offer"].hidden, true);
});

test("Backend предлагает заявку — кнопки появляются", async () => {
    const app = createApp([
        { answer: "Нужна помощь специалиста?", offer_application: true },
    ]);

    await submit(app, "Помогите с энергопотреблением");

    assert.equal(app.elements["application-offer"].hidden, false);
});

test("Согласие отправляет команду оформления заявки", async () => {
    const app = createApp([
        { answer: "Нужна помощь специалиста?", offer_application: true },
        { answer: "Как вас зовут?", offer_application: false },
    ]);

    await submit(app, "Нужна консультация");
    await click(app, "accept-application-button");

    const last = JSON.parse(app.requests.at(-1).body);
    assert.equal(last.message, "Оформить заявку");
    assert.equal(last.session_id, "test-session");
    assert.equal(app.elements["application-offer"].hidden, true);
});

test("Отказ отправляет продолжение консультации", async () => {
    const app = createApp([
        { answer: "Предлагаю специалиста", offer_application: true },
        { answer: "Продолжим консультацию", offer_application: false },
    ]);

    await submit(app, "Вопрос");
    await click(app, "decline-application-button");

    const last = JSON.parse(app.requests.at(-1).body);
    assert.equal(last.message, "Продолжить консультацию");
    assert.equal(app.elements["application-offer"].hidden, true);
});

test("Новый диалог скрывает предложение", async () => {
    const app = createApp([
        { answer: "Предлагаю специалиста", offer_application: true },
    ]);

    await submit(app, "Вопрос");
    assert.equal(app.elements["application-offer"].hidden, false);

    app.elements["new-chat-button"].handlers.click();

    assert.equal(app.elements["application-offer"].hidden, true);
});


test("История загружается через GET без обращения к RAG", async () => {
    const app = createApp([
        { sessions: [{ session_id: "abc123", status: "closed" }] },
        { session_id: "abc123", messages: [
            { role: "user", content: "Привет" },
            { role: "assistant", content: "Здравствуйте" },
        ], application: null },
    ]);
    await app.elements["load-history-button"].handlers.click();
    assert.equal(app.requests[0].url, "/api/sessions");
    assert.equal(app.elements["history-list"].children.length, 1);
    await app.elements["history-list"].children[0].handlers.click();
    assert.equal(app.requests[1].url, "/api/sessions/abc123");
    assert.equal(app.elements["chat-messages"].children.length, 2);
    assert.equal(app.elements["message-input"].disabled, true);
});

test("Возврат из истории восстанавливает текущий диалог", async () => {
    const app = createApp([
        { answer: "Текущий ответ", offer_application: true },
        { sessions: [{ session_id: "old", status: "closed" }] },
        { session_id: "old", messages: [{ role: "user", content: "Старый вопрос" }], application: null },
        { answer: "Продолжение" },
    ]);
    await submit(app, "Текущий вопрос");
    const current = app.elements["chat-messages"].children.length;
    await app.elements["load-history-button"].handlers.click();
    await app.elements["history-list"].children[0].handlers.click();
    assert.equal(app.elements["application-offer"].hidden, true);
    await app.elements["return-to-chat-button"].handlers.click();
    assert.equal(app.elements["chat-messages"].children.length, current);
    assert.equal(app.elements["application-offer"].hidden, false);
    await submit(app, "Продолжаем");
    const req = JSON.parse(app.requests.at(-1).body);
    assert.equal(req.session_id, "test-session");
});

test("Некорректный список истории не удаляет переписку", async () => {
    const app = createApp([{ answer: "Текущий ответ" }, { sessions: null }]);
    await submit(app, "Привет");
    const current = app.elements["chat-messages"].children.length;
    await app.elements["load-history-button"].handlers.click();
    assert.equal(app.elements["chat-messages"].children.length, current);
    assert.match(app.elements["history-status"].textContent, /Не удалось/);
});
