
"use strict";

const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const chatMessages = document.getElementById("chat-messages");
const newChatButton = document.getElementById("new-chat-button");
const applicationOffer = document.getElementById("application-offer");
const acceptApplicationButton = document.getElementById("accept-application-button");
const declineApplicationButton = document.getElementById("decline-application-button");
const loadHistoryButton = document.getElementById("load-history-button");
const historyStatus = document.getElementById("history-status");
const historyList = document.getElementById("history-list");
const historyViewBanner = document.getElementById("history-view-banner");
const returnToChatButton = document.getElementById("return-to-chat-button");

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
let isHistoryLoading = false;
let viewingArchivedSession = false;
let liveChatSnapshot = null;

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
    sendButton.disabled = value || viewingArchivedSession || isHistoryLoading;
    messageInput.disabled = value || viewingArchivedSession || isHistoryLoading;
    newChatButton.disabled = value || isHistoryLoading;
    acceptApplicationButton.disabled = value || viewingArchivedSession || isHistoryLoading;
    declineApplicationButton.disabled = value || viewingArchivedSession || isHistoryLoading;
    loadHistoryButton.disabled = value || isHistoryLoading;
    returnToChatButton.disabled = value || isHistoryLoading;

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

function renderApplicationOffer(data) {
    applicationOffer.hidden = data?.offer_application !== true;
}

async function submitChatMessage(text) {
    if (isSending || isHistoryLoading || viewingArchivedSession || !text.trim()) {
        return;
    }

    const hadOffer = !applicationOffer.hidden;
    applicationOffer.hidden = true;

    addMessage("user", text);
    messageInput.value = "";
    setSending(true);

    const startedAt = performance.now();

    try {
        const data = await sendMessage(text);

        addMessage("assistant", data.answer);
        renderDebug(data, performance.now() - startedAt);
        renderApplication(data.application);
        renderApplicationOffer(data);
    } catch (error) {
        console.error("Chat request failed:", error);

        const errorMessage = error.message === "HTTP 503"
            ? "Сервис консультации сейчас недоступен. Попробуйте позже или обратитесь к специалисту."
            : "Не удалось получить ответ. Проверьте соединение и попробуйте позже.";

        addMessage("assistant", errorMessage);

        // Если отправка выбора не удалась, возвращаем кнопки.
        applicationOffer.hidden = !hadOffer;
    } finally {
        setSending(false);
        messageInput.focus();
    }
}

// Историю получаем отдельно от консультации, не вызывая RAG.
async function historyRequest(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
}

function saveLiveChat() {
    if (liveChatSnapshot !== null) return;
    liveChatSnapshot = {
        messages: [...chatMessages.children],
        applicationStatus: applicationStatus.textContent,
        applicationChildren: [...applicationDetails.children],
        applicationHidden: applicationDetails.hidden,
        offerHidden: applicationOffer.hidden,
        responseTime: responseTime.textContent,
        sources: [...sourceDocuments.children],
    };
}

function exitHistoryView() {
    if (!viewingArchivedSession) return;
    viewingArchivedSession = false;
    historyViewBanner.hidden = true;
    if (liveChatSnapshot !== null) {
        chatMessages.replaceChildren(...liveChatSnapshot.messages);
        applicationStatus.textContent = liveChatSnapshot.applicationStatus;
        applicationDetails.replaceChildren(...liveChatSnapshot.applicationChildren);
        applicationDetails.hidden = liveChatSnapshot.applicationHidden;
        applicationOffer.hidden = liveChatSnapshot.offerHidden;
        responseTime.textContent = liveChatSnapshot.responseTime;
        sourceDocuments.replaceChildren(...liveChatSnapshot.sources);
    }
    liveChatSnapshot = null;
    setSending(false);
    messageInput.focus();
}

async function showArchivedSession(archivedId) {
    if (isSending || isHistoryLoading) return;
    isHistoryLoading = true;
    setSending(false);
    historyStatus.textContent = "Загружаем диалог...";
    try {
        const data = await historyRequest(`/api/sessions/${encodeURIComponent(archivedId)}`);
        if (!data || !Array.isArray(data.messages)) {
            throw new Error("Некорректный формат истории");
        }
        saveLiveChat();
        viewingArchivedSession = true;
        historyViewBanner.hidden = false;
        chatMessages.replaceChildren();
        for (const entry of data.messages) {
            if ((entry.role === "user" || entry.role === "assistant") && typeof entry.content === "string") {
                addMessage(entry.role, entry.content);
            }
        }
        if (chatMessages.children.length === 0) {
            addMessage("assistant", "В этом диалоге пока нет сообщений.");
        }
        applicationOffer.hidden = true;
        renderApplication(data.application);
        responseTime.textContent = "—";
        sourceDocuments.replaceChildren();
        historyStatus.textContent = "История открыта только для просмотра.";
    } catch (error) {
        console.error("History request failed:", error);
        historyStatus.textContent = "Не удалось загрузить диалог. Попробуйте снова.";
    } finally {
        isHistoryLoading = false;
        setSending(false);
    }
}

loadHistoryButton.addEventListener("click", async () => {
    if (isSending || isHistoryLoading) return;
    isHistoryLoading = true;
    setSending(false);
    historyStatus.textContent = "Загружаем список диалогов...";
    try {
        const data = await historyRequest("/api/sessions");
        if (!data || !Array.isArray(data.sessions)) {
            throw new Error("Некорректный формат списка сессий");
        }
        historyList.replaceChildren();
        for (const item of data.sessions) {
            if (typeof item.session_id !== "string") continue;
            const button = document.createElement("button");
            button.type = "button";
            const status = item.status === "closed" ? "завершён" : "активен";
            button.textContent = `Диалог ${item.session_id.slice(0, 8)}… (${status})`;
            button.addEventListener("click", () => showArchivedSession(item.session_id));
            historyList.appendChild(button);
        }
        historyList.hidden = false;
        historyStatus.textContent = historyList.children.length
            ? "Выберите диалог для просмотра." : "Сохранённых диалогов пока нет.";
    } catch (error) {
        console.error("History list request failed:", error);
        historyStatus.textContent = "Не удалось получить историю. Попробуйте снова.";
    } finally {
        isHistoryLoading = false;
        setSending(false);
    }
});

returnToChatButton.addEventListener("click", () => exitHistoryView());

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitChatMessage(messageInput.value.trim());
});

acceptApplicationButton.addEventListener("click", () => {
    submitChatMessage("Оформить заявку");
});

declineApplicationButton.addEventListener("click", () => {
    submitChatMessage("Продолжить консультацию");
});

newChatButton.addEventListener("click", () => {
    if (isSending || isHistoryLoading) return;
    exitHistoryView();
    sessionId = crypto.randomUUID();

    chatMessages.replaceChildren();
    applicationOffer.hidden = true;

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
