import { onDocumentUpdated } from "firebase-functions/v2/firestore";
import { defineSecret } from "firebase-functions/params";
import { getFirestore } from "firebase-admin/firestore";
import { initializeApp } from "firebase-admin/app";

initializeApp();

const twilioAccountSid = defineSecret("TWILIO_ACCOUNT_SID");
const twilioAuthToken = defineSecret("TWILIO_AUTH_TOKEN");
const twilioWhatsAppFrom = defineSecret("TWILIO_WHATSAPP_FROM");
const twilioContentSid = defineSecret("TWILIO_CONTENT_SID");

const statusLabels: Record<string, string> = {
  "جديد": "تم استلام طلبك",
  "قيد التحضير": "طلبك قيد التحضير",
  "تم التوصيل": "تم توصيل طلبك",
  "ملغى": "تم إلغاء طلبك",
};

function normalizeWhatsAppNumber(value: unknown) {
  const digits = String(value ?? "").replace(/\D/g, "");
  return digits.length >= 8 && digits.length <= 15 ? `+${digits}` : null;
}

export const notifyOrderStatus = onDocumentUpdated(
  {
    document: "orders/{orderId}",
    region: "europe-west1",
    secrets: [twilioAccountSid, twilioAuthToken, twilioWhatsAppFrom, twilioContentSid],
    retry: true,
  },
  async (event) => {
    const before = event.data?.before.data();
    const after = event.data?.after.data();
    if (!before || !after || before.status === after.status) return;

    const to = normalizeWhatsAppNumber(after.customerPhone);
    const status = String(after.status ?? "");
    if (!to || !statusLabels[status]) return;

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
    } else {
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

    await getFirestore().collection("orders").doc(event.params.orderId).set({
      whatsappNotification: { status, sentAt: new Date().toISOString(), provider: "twilio" },
    }, { merge: true });
  },
);
