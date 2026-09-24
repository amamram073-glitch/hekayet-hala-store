import { initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, OAuthProvider, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";

const env = import.meta.env;
const firebaseConfig = {
  apiKey: env.VITE_FIREBASE_API_KEY ?? "",
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN ?? "",
  projectId: env.VITE_FIREBASE_PROJECT_ID ?? "",
  storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET ?? "",
  messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID ?? "",
  appId: env.VITE_FIREBASE_APP_ID ?? "",
};

const requiredFirebaseValues = [
  firebaseConfig.apiKey,
  firebaseConfig.authDomain,
  firebaseConfig.projectId,
  firebaseConfig.appId,
];
const isFirebaseConfigured = requiredFirebaseValues.every(
  (value) => value.trim().length > 0 && !/replace|your_|placeholder|123456789/i.test(value),
);

let app: FirebaseApp | null = null;
let auth: Auth | null = null;
let db: Firestore | null = null;
let googleProvider: GoogleAuthProvider | null = null;
let appleProvider: OAuthProvider | null = null;

if (isFirebaseConfigured) {
  try {
    app = initializeApp(firebaseConfig);
    auth = getAuth(app);
    db = getFirestore(app);
    googleProvider = new GoogleAuthProvider();
    appleProvider = new OAuthProvider("apple.com");
  } catch (error) {
    console.error("تعذر تهيئة Firebase. تحقق من إعدادات المشروع.", error);
  }
}

const firebaseReady = Boolean(isFirebaseConfigured && app && auth && db);
if (!firebaseReady) {
  console.info("Firebase غير مهيأ: ستظل المصادقة والطلبات الداخلية معطلة، ويمكن استخدام الطلب عبر واتساب كضيف.");
}

export { auth, db, googleProvider, appleProvider, firebaseReady as isFirebaseConfigured };
export const adminEmails = (env.VITE_ADMIN_EMAILS ?? "")
  .split(",")
  .map((email: string) => email.trim().toLowerCase())
  .filter(Boolean);
export const defaultWhatsappNumber = (env.VITE_WHATSAPP_NUMBER ?? "").replace(/[^\d]/g, "");
