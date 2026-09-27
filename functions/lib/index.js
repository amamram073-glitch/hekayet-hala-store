"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.notifyOrderStatus = void 0;
const firestore_1 = require("firebase-functions/v2/firestore");
const params_1 = require("firebase-functions/params");
const firestore_2 = require("firebase-admin/firestore");
const app_1 = require("firebase-admin/app");
(0, app_1.initializeApp)();
const twilioAccountSid = (0, params_1.defineSecret)("TWILIO_ACCOUNT_SID");
const twilioAuthToken = (0, params_1.defineSecret)("TWILIO_AUTH_TOKEN");
const twilioWhatsAppFrom = (0, params_1.defineSecret)("TWILIO_WHATSAPP_FROM");
const twilioContentSid = (0, params_1.defineSecret)("TWILIO_CONTENT_SID");
const statusLabels = {
    "جديد": "تم استلام طلبك",
    "قيد التحضير": "طلبك قيد التحضير",
    "تم التوصيل": "تم توصيل طلبك",
    "ملغى": "تم إلغاء طلبك",
};
function normalizeWhatsAppNumber(value) {
    const digits = String(value ?? "").replace(/\D/g, "");
    return digits.length >= 8 && digits.length <= 15 ? `+${digits}` : null;
}
exports.notifyOrderStatus = (0, firestore_1.onDocumentUpdated)({
    document: "orders/{orderId}",
    region: "europe-west1",
    secrets: [twilioAccountSid, twilioAuthToken, twilioWhatsAppFrom, twilioContentSid],
    retry: true,
}, async (event) => {
    const before = event.data?.before.data();
    const after = event.data?.after.data();
    if (!before || !after || before.status === after.status)
        return;
    const to = normalizeWhatsAppNumber(after.customerPhone);
    const status = String(after.status ?? "");
    if (!to || !statusLabels[status])
        return;
    const sid = twilioAccountSid.value();
    const token = twilioAuthToken.value();
    const from = normalizeWhatsAppNumber(twilioWhatsAppFrom.value());
    if (!sid || !token || !from) {
        console.error("Twilio secrets are not configured.");
        return;
    }
    const orderId = String(after.id ?? event.params.orderId);
    const total = Number(after.total ?? 0);
    const contentSid = twilioContentSid.value();
    const body = new URLSearchParams({
        From: `whatsapp:${from}`,
        To: `whatsapp:${to}`,
    });
    if (contentSid) {
        body.set("ContentSid", contentSid);
        body.set("ContentVariables", JSON.stringify({ "1": orderId, "2": statusLabels[status], "3": String(total) }));
    }
    else {
        body.set("Body", `حكاية حلا\n${statusLabels[status]} لطلبك رقم ${orderId}.\nالإجمالي: ${total} د.إ`);
    }
    const response = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${encodeURIComponent(sid)}/Messages.json`, {
        method: "POST",
        headers: {
            Authorization: `Basic ${Buffer.from(`${sid}:${token}`).toString("base64")}`,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body,
    });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Twilio request failed (${response.status}): ${errorText.slice(0, 500)}`);
    }
    await (0, firestore_2.getFirestore)().collection("orders").doc(event.params.orderId).set({
        whatsappNotification: { status, sentAt: new Date().toISOString(), provider: "twilio" },
    }, { merge: true });
});
//# sourceMappingURL=index.js.map