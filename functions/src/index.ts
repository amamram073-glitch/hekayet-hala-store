import { onDocumentUpdated } from "firebase-functions/v2/firestore";
import { onCall, HttpsError } from "firebase-functions/v2/https";
import { defineSecret } from "firebase-functions/params";
import { getFirestore } from "firebase-admin/firestore";
import { initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

initializeApp();

const twilioAccountSid = defineSecret("TWILIO_ACCOUNT_SID");
const twilioAuthToken = defineSecret("TWILIO_AUTH_TOKEN");
const twilioWhatsAppFrom = defineSecret("TWILIO_WHATSAPP_FROM");
const twilioContentSid = defineSecret("TWILIO_CONTENT_SID");
const firestore = getFirestore();

type StaffPermission = "orders_read" | "orders_update" | "inventory_read" | "inventory_write" | "products_write" | "content_write" | "reports_read" | "staff_manage";
const staffPermissions: StaffPermission[] = ["orders_read", "orders_update", "inventory_read", "inventory_write", "products_write", "content_write", "reports_read", "staff_manage"];

async function requireOwner(uid: string | undefined) {
  if (!uid) throw new HttpsError("unauthenticated", "يجب تسجيل الدخول أولًا.");
  const owner = await firestore.doc(`admins/${uid}`).get();
  if (!owner.exists) throw new HttpsError("permission-denied", "هذه العملية متاحة للمسؤول الرئيس فقط.");
}

function cleanPermissions(input: unknown) {
  const values = input && typeof input === "object" ? input as Record<string, unknown> : {};
  return Object.fromEntries(staffPermissions.map((key) => [key, values[key] === true]));
}

export const listStaff = onCall({ region: "europe-west1" }, async (request) => {
  await requireOwner(request.auth?.uid);
  const snapshot = await firestore.collection("staff").orderBy("createdAt", "desc").get();
  return snapshot.docs.map((item) => ({ uid: item.id, ...item.data() }));
});

export const createStaffUser = onCall({ region: "europe-west1" }, async (request) => {
  await requireOwner(request.auth?.uid);
  const data = request.data as { email?: string; password?: string; displayName?: string; permissions?: unknown };
  const email = String(data.email ?? "").trim().toLowerCase();
  const password = String(data.password ?? "");
  if (!/^\S+@\S+\.\S+$/.test(email) || password.length < 8) throw new HttpsError("invalid-argument", "أدخل بريدًا صحيحًا وكلمة مرور من 8 أحرف على الأقل.");
  try {
    const user = await getAuth().createUser({ email, password, displayName: String(data.displayName ?? "موظف").trim().slice(0, 80) });
    await firestore.doc(`staff/${user.uid}`).set({ email, displayName: user.displayName ?? "موظف", active: true, role: "staff", permissions: cleanPermissions(data.permissions), createdAt: new Date().toISOString(), createdBy: request.auth?.uid });
    return { uid: user.uid };
  } catch (error) {
    console.error(error);
    throw new HttpsError("already-exists", "تعذر إنشاء الموظف؛ قد يكون البريد مستخدمًا بالفعل.");
  }
});

export const updateStaffUser = onCall({ region: "europe-west1" }, async (request) => {
  await requireOwner(request.auth?.uid);
  const data = request.data as { uid?: string; displayName?: string; active?: boolean; permissions?: unknown };
  const uid = String(data.uid ?? "");
  if (!uid || uid === request.auth?.uid) throw new HttpsError("invalid-argument", "معرّف الموظف غير صالح.");
  await getAuth().updateUser(uid, { displayName: String(data.displayName ?? "موظف").trim().slice(0, 80), disabled: data.active === false });
  await firestore.doc(`staff/${uid}`).set({ displayName: String(data.displayName ?? "موظف").trim().slice(0, 80), active: data.active !== false, permissions: cleanPermissions(data.permissions), updatedAt: new Date().toISOString(), updatedBy: request.auth?.uid }, { merge: true });
  return { uid };
});

export const deleteStaffUser = onCall({ region: "europe-west1" }, async (request) => {
  await requireOwner(request.auth?.uid);
  const uid = String((request.data as { uid?: string }).uid ?? "");
  if (!uid || uid === request.auth?.uid) throw new HttpsError("invalid-argument", "لا يمكن حذف هذا الحساب.");
  await getAuth().deleteUser(uid);
  await firestore.doc(`staff/${uid}`).delete();
  return { uid };
});

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

    await firestore.collection("orders").doc(event.params.orderId).set({
      whatsappNotification: { status, sentAt: new Date().toISOString(), provider: "twilio" },
    }, { merge: true });
  },
);
