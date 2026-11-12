
"use strict";

const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const chatMessages = document.getElementById("chat-messages");
const newChatButton = document.getElementById("new-chat-button");

const debugToggle = document.getElementById("debug-toggle");
const debugDetails = document.getElementById("debug-details");
const responseTime = document.getElementById("response-time");
const sourceDocuments = document.getElementById("source-documents");

const applicationStatus = document.getElementById("application-status");
const applicationDetails = document.getElementById("application-details");

// Предварительный адрес API.
// Согласуем его с участником А при интеграции.
const CHAT_API_URL = "/api/chat";

let sessionId = crypto.randomUUID();
let isSending = false;

function addMessage(role, text) {
    const element = document.createElement("div");

    element.className = `message ${
        role === "user" ? "user-message" : "assistant-message"
    }`;

    // textContent не выполняет HTML или JavaScript
    // из сообщений пользователя или модели.
    element.textContent = text;

    chatMessages.appendChild(element);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function setSending(value) {
    isSending = value;
    sendButton.disabled = value;
    messageInput.disabled = value;
    newChatButton.disabled = value;

    sendButton.textContent = value
        ? "Отправка..."
        : "Отправить";
}

function renderDebug(data, elapsedMilliseconds) {
    responseTime.textContent =
        `${Math.round(elapsedMilliseconds)} мс`;

    sourceDocuments.replaceChildren();

    const documents = Array.isArray(data.sources)
        ? data.sources
        : [];

    for (const documentName of documents) {
        if (typeof documentName !== "string") {
            continue;
        }

        const item = document.createElement("li");
        item.textContent = documentName;
        sourceDocuments.appendChild(item);
    }

    if (sourceDocuments.children.length === 0) {
        const item = document.createElement("li");
        item.textContent = "Документы не указаны";
        sourceDocuments.appendChild(item);
    }
}

function renderApplication(application) {
    applicationDetails.replaceChildren();

    if (!application || application.ready !== true) {
        applicationStatus.textContent =
            "Заявка пока не оформлена.";
        applicationDetails.hidden = true;
        return;
    }

    applicationStatus.textContent = "Заявка сформирована, но ещё не отправлена менеджеру.";
    applicationDetails.hidden = false;

    const fields = [
        ["ФИО", application.contacts?.full_name],
        ["Телефон", application.contacts?.phone],
        ["Компания", application.contacts?.company],
        ["Проблема", application.summary?.problem],
        ["Обстоятельства", application.summary?.circumstances],
        ["Обсуждение", application.summary?.discussed_solution],
    ];

    for (const [label, value] of fields) {
        if (typeof value !== "string" || !value.trim()) {
            continue;
        }

        const paragraph = document.createElement("p");
        paragraph.textContent = `${label}: ${value}`;
        applicationDetails.appendChild(paragraph);
    }

    const questions = application.summary?.open_questions;

    if (Array.isArray(questions) && questions.length > 0) {
        const paragraph = document.createElement("p");

        paragraph.textContent =
            `Открытые вопросы: ${questions.join("; ")}`;

        applicationDetails.appendChild(paragraph);
    }
}

async function sendMessage(text) {
    const response = await fetch(CHAT_API_URL, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            session_id: sessionId,
            message: text,
        }),
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    if (
        !data ||
        typeof data.answer !== "string"
    ) {
        throw new Error("Некорректный ответ сервера");
    }

    return data;
}

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (isSending) {
        return;
    }

    const text = messageInput.value.trim();

    if (!text) {
        return;
    }

    addMessage("user", text);
    messageInput.value = "";
    setSending(true);

    const startedAt = performance.now();

    try {
        const data = await sendMessage(text);

        addMessage("assistant", data.answer);

        renderDebug(
            data,
            performance.now() - startedAt,
        );

        renderApplication(data.application);
    } catch (error) {
        console.error("Chat request failed:", error);

        addMessage(
            "assistant",
            "Не удалось получить ответ от сервиса консультации. " +
            "Попробуйте позже.",
        );
    } finally {
        setSending(false);
        messageInput.focus();
    }
});

newChatButton.addEventListener("click", () => {
    sessionId = crypto.randomUUID();

    chatMessages.replaceChildren();

    addMessage(
        "assistant",
        "Здравствуйте! Я ИИ-консультант МТС Energytool. " +
        "Задайте вопрос об энергопотреблении или напишите «Оформить заявку», " +
        "чтобы оставить контакты специалисту.",
    );

    applicationStatus.textContent =
        "Заявка пока не оформлена.";

    applicationDetails.replaceChildren();
    applicationDetails.hidden = true;

    responseTime.textContent = "—";
    sourceDocuments.replaceChildren();
    messageInput.value = "";
    messageInput.focus();
});

debugToggle.addEventListener("change", () => {
    debugDetails.hidden = !debugToggle.checked;
});
