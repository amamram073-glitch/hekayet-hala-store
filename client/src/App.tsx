
import { useState, useEffect, useRef } from "react";
import { trpc } from "./lib/trpc";
import { catalogSeed } from "@shared/catalog";
import { auth, db, isFirebaseConfigured, defaultWhatsappNumber } from "./firebase";
import { onAuthStateChanged, signOut, signInWithEmailAndPassword, type User } from "firebase/auth";
import { collection, addDoc, getDocs, serverTimestamp, doc, updateDoc, getDoc, onSnapshot, query, orderBy } from "firebase/firestore";
import { isValidE164PhoneNumber, normalizePhoneNumber } from "./lib/phoneAuth";
import { getCyclicSlideIndex } from "./lib/familySlider";
import AdminPanel from "./components/AdminPanel";
const heroBg = "/manus-storage/hero_842b2022.webp";
const cheesecakeCup = "/manus-storage/cheesecake_558e507c.jpeg";
const loginDessertImage = "/manus-storage/cheesecake-box_2a61d9d0.webp";

type Screen = "login" | "main" | "admin";
type OrderMethod = "whatsapp" | "internal";

interface Product {
  id: number;
  slug: string;
  name: string;
  price: number;
  image: string;
  desc: string;
  tag: string;
  collection: "classic" | "family";
}

const fallbackProducts: Product[] = catalogSeed.map((product, index) => ({
  id: index + 1,
  slug: product.slug,
  name: product.name,
  price: product.price,
  image: product.image,
  desc: product.description,
  tag: product.tag,
  collection: product.collection,
}));

export default function App() {
  const catalogQuery = trpc.catalog.list.useQuery(undefined, { retry: false });
  const isAdminPreview = import.meta.env.DEV && new URLSearchParams(window.location.search).get("admin") === "preview";
  const databaseProducts: Product[] = catalogQuery.data?.map((product) => ({
    id: product.id,
    slug: product.slug,
    name: product.name,
    price: product.price,
    image: product.image,
    desc: product.description,
    tag: product.tag,
    collection: product.collection,
  })) ?? fallbackProducts;
  const [firestoreProducts, setFirestoreProducts] = useState<Product[]>([]);
  const products: Product[] = firestoreProducts.length > 0 ? firestoreProducts : databaseProducts;
  const familyProducts = products.filter((product) => product.collection === "family");
  const [screen, setScreen] = useState<Screen>(isAdminPreview ? "admin" : "main");
  const [user, setUser] = useState<User | any>(null);
  const [isAdmin, setIsAdmin] = useState(isAdminPreview);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [cart, setCart] = useState<{id:number, q:number}[]>(() => {
    const saved = localStorage.getItem("hekaya_cart_v3");
    return saved ? JSON.parse(saved) : [];
  });
  const [showToast, setShowToast] = useState("");
  const [orderMethod, setOrderMethod] = useState<OrderMethod>(() => {
    const saved = localStorage.getItem("hekaya_order_method") as OrderMethod | null;
    return saved === "internal" && !isFirebaseConfigured ? "whatsapp" : saved || "whatsapp";
  });
  const [orders, setOrders] = useState<any[]>([]);
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [deliveryNote, setDeliveryNote] = useState("");
  const [loginPhone, setLoginPhone] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [phoneLoginMessage, setPhoneLoginMessage] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [tilt, setTilt] = useState({ rx: 2, ry: 0 });
  const [activeFamilySlide, setActiveFamilySlide] = useState(0);
  const [siteContent, setSiteContent] = useState({
    heroTitle: "حلويات فلسطينية أصيلة",
    heroDescription: "من قلب فلسطين إلى مائدتك، وصفات جداتنا بطعم الأصالة",
    heroBadge: "حلويات فلسطينية",
    aboutTitle: "حكاية حلا من فلسطين",
    aboutText: "نقدّم حلويات فلسطينية أصيلة بوصفات عائلية ومكونات مختارة.",
    faq: [] as Array<{ question: string; answer: string }>,
    contactPhone: "",
    contactEmail: "",
    contactAddress: "",
    deliveryPolicy: "سيتم التنسيق معكم عبر واتساب.",
    returnPolicy: "يرجى التواصل معنا فورًا عند وجود أي مشكلة في الطلب.",
    privacyPolicy: "نستخدم بيانات التواصل لإتمام الطلب فقط.",
  });
  const currentFamilyProduct = familyProducts[activeFamilySlide] ?? familyProducts[0];

  // Mouse parallax for 3D
  useEffect(() => {
    const handleMouse = (e: MouseEvent) => {
      const x = (e.clientX / window.innerWidth - 0.5) * 2;
      const y = (e.clientY / window.innerHeight - 0.5) * 2;
      setMousePos({ x, y });
      setTilt({ rx: 2 + y * -1.2, ry: x * 2 });
    };
    window.addEventListener("mousemove", handleMouse);
    return () => window.removeEventListener("mousemove", handleMouse);
  }, []);

  useEffect(() => {
    if (screen !== "login" || familyProducts.length < 2) return;
    const interval = window.setInterval(() => {
      setActiveFamilySlide((current) => getCyclicSlideIndex(current, 1, familyProducts.length));
    }, 4200);
    return () => window.clearInterval(interval);
  }, [screen, familyProducts.length]);

  useEffect(() => {
    if (!db) return;
    const productsQuery = query(collection(db, "products"), orderBy("id", "asc"));
    const unsubscribeProducts = onSnapshot(productsQuery, (snapshot) => {
      setFirestoreProducts(snapshot.docs.map((item) => ({ id: Number(item.data().id), ...item.data() } as Product)));
    }, (error) => console.error("تعذر تحميل منتجات Firebase", error));
    const unsubscribeContent = onSnapshot(doc(db, "siteContent", "main"), (snapshot) => {
      if (snapshot.exists()) setSiteContent((current) => ({ ...current, ...snapshot.data() }));
    }, (error) => console.error("تعذر تحميل محتوى الموقع", error));
    return () => { unsubscribeProducts(); unsubscribeContent(); };
  }, []);

  const moveFamilySlide = (direction: -1 | 1) => {
    if (familyProducts.length < 2) return;
    setActiveFamilySlide((current) => getCyclicSlideIndex(current, direction, familyProducts.length));
  };

  // Persist cart
  useEffect(() => {
    localStorage.setItem("hekaya_cart_v3", JSON.stringify(cart));
  }, [cart]);

  useEffect(() => {
    localStorage.setItem("hekaya_order_method", orderMethod);
  }, [orderMethod]);

  // Real Firebase Auth listener
  useEffect(() => {
    if (!isFirebaseConfigured || !auth) {
      const guestSession = localStorage.getItem("hekaya_guest_session");
      if (guestSession) {
        setUser(JSON.parse(guestSession));
        setScreen("main");
      }
      return;
    }
    const unsub = onAuthStateChanged(auth, (u) => {
      if (u) {
        setUser(u);
        setScreen("main");
      } else {
        const guestSession = localStorage.getItem("hekaya_guest_session");
        if (guestSession) {
          setUser(JSON.parse(guestSession));
          setScreen("main");
        } else {
          setUser(null);
          setScreen("login");
        }
      }
    });
    return () => unsub();
  }, []);

  useEffect(() => {
    let active = true;
    setIsAdmin(isAdminPreview);
    if (isAdminPreview) return;
    if (!isFirebaseConfigured || !db || !user?.uid || String(user.uid).startsWith("guest_")) return;
    getDoc(doc(db, "admins", user.uid))
      .then((snapshot) => { if (active) setIsAdmin(snapshot.exists()); })
      .catch((error) => console.error("تعذر التحقق من صلاحية المشرف", error));
    return () => { active = false; };
  }, [user?.uid, isAdminPreview]);

  const handlePhoneLoginPreparation = () => {
    if (!isValidE164PhoneNumber(loginPhone)) {
      setPhoneLoginMessage("أدخل رقم الجوال بصيغته الدولية مع مفتاح الدولة، مثل ‎+971501234567.");
      return;
    }
    setLoginPhone(normalizePhoneNumber(loginPhone));
    setPhoneLoginMessage("واجهة الرقم ورمز التحقق جاهزة. لن يُرسل رمز SMS أو يُنشأ دخول حقيقي حتى يُربط مزود الرسائل.");
  };

  const handleAdminLogin = async () => {
    if (!auth || !isFirebaseConfigured || !adminEmail.trim() || adminPassword.length < 8) {
      setPhoneLoginMessage("أدخل بريد المشرف وكلمة مرور من 8 أحرف على الأقل.");
      return;
    }
    try {
      await signInWithEmailAndPassword(auth, adminEmail.trim(), adminPassword);
      setPhoneLoginMessage("");
    } catch (error) {
      console.error(error);
      setPhoneLoginMessage("تعذر تسجيل الدخول. تحقق من البيانات أو إعداد Firebase Authentication.");
    }
  };

  const handleLogout = async () => {
    if (isFirebaseConfigured && auth) await signOut(auth);
    localStorage.removeItem("hekaya_guest_session");
    setUser(null);
    setScreen("login");
  };

  const continueAsGuest = () => {
    const guest = { uid: `guest_${crypto.randomUUID()}`, displayName: "ضيف حكاية حلا", email: "" };
    localStorage.setItem("hekaya_guest_session", JSON.stringify(guest));
    setUser(guest);
    setScreen("main");
  };

  const addToCart = (id: number) => {
    setCart(prev => {
      const found = prev.find(c => c.id === id);
      if (found) return prev.map(c => c.id === id ? {...c, q: c.q+1} : c);
      return [...prev, {id, q: 1}];
    });
    toast("تمت الإضافة إلى السلة ✓");
  };

  const updateQty = (id: number, delta: number) => {
    setCart(prev => prev.map(c => c.id === id ? {...c, q: Math.max(1, c.q+delta)} : c).filter(c => c.q>0));
  };

  const removeFromCart = (id: number) => {
    setCart(prev => prev.filter(c => c.id !== id));
  };

  const cartTotal = cart.reduce((sum, c) => {
    const p = products.find(pr => pr.id === c.id);
    return sum + (p ? p.price * c.q : 0);
  }, 0);

  const cartCount = cart.reduce((s,c)=>s+c.q,0);

  const toast = (msg: string) => {
    setShowToast(msg);
    setTimeout(()=>setShowToast(""), 3000);
  };

  useEffect(() => {
    if (screen !== "admin" || !isAdmin || !db) return;
    let active = true;
    getDocs(collection(db, "orders"))
      .then((snapshot) => {
        if (!active) return;
        const remoteOrders = snapshot.docs.map((orderDoc) => ({
          ...orderDoc.data(),
          firestoreDocId: orderDoc.id,
        }));
        remoteOrders.sort((a: any, b: any) => String(b.date ?? "").localeCompare(String(a.date ?? "")));
        setOrders(remoteOrders);
      })
      .catch((error) => {
        console.error(error);
        toast("تعذر تحميل الطلبات. تحقق من تسجيل دخول المشرف وقواعد Firestore.");
      });
    return () => { active = false; };
  }, [screen, isAdmin]);

  const updateOrderStatus = async (order: any, status: string) => {
    if (!isAdmin || !db || !order.firestoreDocId) {
      toast("لا تملك صلاحية تعديل هذا الطلب.");
      return;
    }
    try {
      await updateDoc(doc(db, "orders", order.firestoreDocId), { status });
      setOrders((prev) => prev.map((item) => item.firestoreDocId === order.firestoreDocId ? { ...item, status } : item));
      toast("تم تحديث حالة الطلب.");
    } catch (error) {
      console.error(error);
      toast("تعذر تحديث الحالة. تحقق من قواعد Firestore.");
    }
  };

  // إرسال الطلب - واتساب أو داخلي
  const handleOrder = async () => {
    if (cart.length === 0) { toast("السلة فارغة"); return; }
    if (orderMethod === "internal" && (!user || !isFirebaseConfigured || !auth?.currentUser || auth.currentUser.uid !== user.uid)) {
      toast("الطلبات الداخلية تتطلب تسجيل دخول حقيقي وإعداد Firebase. استخدم واتساب أو أعد الإعداد.");
      return;
    }
    if (orderMethod === "whatsapp" && !/^\d{8,15}$/.test(defaultWhatsappNumber)) {
      toast("رقم واتساب المتجر غير مضبوط. يجب تحديد VITE_WHATSAPP_NUMBER قبل النشر.");
      return;
    }
    const normalizedCustomerPhone = customerPhone.replace(/[^\d+]/g, "");
    if (!customerName.trim() || normalizedCustomerPhone.replace(/\D/g, "").length < 8) {
      toast("أدخل اسمك ورقم هاتفك للتواصل بشأن الطلب.");
      return;
    }

    const orderDetails = cart.map(c => {
      const p = products.find(pr => pr.id === c.id);
      return `${p?.name} x${c.q} = ${p ? p.price * c.q : 0} د.إ`;
    }).join("\n");

    const order = {
      id: "ORD" + Date.now(),
      userId: user?.uid ?? null,
      user: user?.email || normalizedCustomerPhone,
      userName: customerName.trim(),
      customerPhone: normalizedCustomerPhone,
      deliveryNote: deliveryNote.trim(),
      items: cart.map((item) => {
        const product = products.find((p) => p.id === item.id);
        return { id: item.id, name: product?.name ?? "منتج", quantity: item.q, unitPrice: product?.price ?? 0 };
      }),
      details: orderDetails,
      total: cartTotal,
      method: orderMethod,
      date: new Date().toISOString(),
      status: "جديد"
    };

    // حفظ في Firestore إذا مُعد
    if (orderMethod === "internal" && isFirebaseConfigured && db && user) {
      try {
        await addDoc(collection(db, "orders"), { ...order, createdAt: serverTimestamp() });
      } catch (e) {
        console.error(e);
        toast("تعذر حفظ الطلب. تحقق من إعدادات Firestore وقواعد الأمان، ولم يتم تأكيد الطلب.");
        return;
      }
    }

    if (orderMethod === "internal") setOrders((prev) => [order, ...prev]);

    if (orderMethod === "whatsapp") {
      const message = `مرحبا حكاية حلا\nطلب جديد:\n${orderDetails}\nالمجموع: ${cartTotal} د.إ\nالاسم: ${order.userName}\nهاتف العميل: ${normalizedCustomerPhone}\nالعنوان/ملاحظات التوصيل: ${deliveryNote.trim() || "سيتم التنسيق عبر الهاتف"}\nرقم الطلب: ${order.id}`;
      const url = `https://wa.me/${defaultWhatsappNumber}?text=${encodeURIComponent(message)}`;
      window.location.assign(url);
    } else {
      toast(`تم استلام طلبك ✓ رقم: ${order.id}`);
      setScreen("main");
    }

    setCart([]);
  };

  // make sure to consider if you need authentication for certain routes
  return (
    <div dir="rtl" className="min-h-screen max-w-[100vw] bg-[#FFFBF5] text-[#1A0A05] antialiased overflow-x-hidden selection:bg-[#C9A86A]/30" style={{ fontFamily: "'Tajawal', system-ui, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800;900&family=Amiri:wght@400;700&display=swap');
        *{ -webkit-font-smoothing: antialiased; }
        html, body { overflow-x: hidden; max-width: 100vw; }
        @keyframes floatY { 0%,100%{ transform: translateY(0px) rotate(-1deg);} 50%{ transform: translateY(-14px) rotate(1deg);} }
        @keyframes kenBurns { 0%{ transform: scale(1) } 100%{ transform: scale(1.06) } }
        @keyframes fadeInUp { from{ opacity:0; transform: translateY(24px)} to{ opacity:1; transform: translateY(0)} }
        @keyframes familySlideIn { from{ opacity:0.55; transform: scale(1.025) } to{ opacity:1; transform: scale(1) } }
        .tatreez {
          background-image:
            radial-gradient(circle at 2px 2px, rgba(201,168,106,0.18) 1px, transparent 0),
            linear-gradient(45deg, rgba(193,39,45,0.06) 25%, transparent 25%, transparent 75%, rgba(193,39,45,0.06) 75%),
            linear-gradient(-45deg, rgba(20,153,84,0.05) 25%, transparent 25%, transparent 75%, rgba(20,153,84,0.05) 75%);
          background-size: 22px 22px, 44px 44px, 44px 44px;
        }
      `}</style>

      {/* LOGIN SCREEN - فخمة 3D */}
      {screen === "login" && (
        <div className="relative w-full h-[100dvh] min-h-[680px] overflow-hidden bg-[#0e0705]">
          <div className="absolute inset-0 overflow-hidden">
            <img src={heroBg} alt="حكاية حلا" className="absolute inset-0 w-full h-full object-cover" style={{ animation: "kenBurns 14s ease-in-out infinite alternate" }} />
            <div className="absolute inset-0 bg-[#1A0A05]/85 backdrop-blur-[1px]" />
            <div className="absolute inset-0 tatreez opacity-[0.25] mix-blend-soft-light" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-black/50" />
            <div className="absolute w-[560px] h-[560px] rounded-full blur-[90px] opacity-[0.2] pointer-events-none" style={{ background: "radial-gradient(circle, #C9A86A 0%, transparent 70%)", left: "50%", top: "60%", transform: `translate(-50%, -50%) translate(${mousePos.x*20}px, ${mousePos.y*12}px)` }} />
          </div>

          <div className="relative z-10 w-full h-full flex flex-col items-center justify-center px-4">
            <div className="mb-4 max-w-[400px] px-3 py-2 rounded-xl bg-amber-500/15 border border-amber-500/25 text-amber-100 text-[11px] text-center leading-5">تسجيل الجوال عبر SMS قيد الإعداد. لن يُرسل رمز تحقق قبل ربط مزود الرسائل.</div>

            <div ref={null} className="w-full max-w-[400px] rounded-[28px] border border-[#C9A86A]/20 bg-white/[0.06] backdrop-blur-[24px] shadow-[0_24px_80px_rgba(0,0,0,0.6),inset_0_1px_0_rgba(255,255,255,0.12)] p-7 sm:p-8" style={{ transform: `perspective(1200px) rotateX(${tilt.rx}deg) rotateY(${tilt.ry}deg)`, transformStyle: "preserve-3d" }}>
              <div className="flex flex-col items-center text-center">
                <div className="w-14 h-14 rounded-full bg-gradient-to-br from-[#C9A86A] to-[#8A6A2E] grid place-items-center text-white font-black text-[20px] shadow-[0_8px_24px_rgba(201,168,106,0.35)]">ح</div>
                <h1 className="mt-4 text-[28px] font-black text-white tracking-tight" style={{ fontFamily: "'Amiri', serif" }}>حكاية حلا</h1>
                <p className="mt-1 text-[13px] text-[#C9A86A] font-bold tracking-[0.2em]">HEKAYET HALA</p>

                {currentFamilyProduct && <div className="mt-6 w-[220px] sm:w-[250px]">
                  <div className="relative h-[158px] sm:h-[172px] overflow-hidden rounded-[22px] border border-white/15 bg-white/10 shadow-[0_16px_40px_rgba(0,0,0,0.4)]">
                    <img key={currentFamilyProduct.slug} src={currentFamilyProduct.image || loginDessertImage} alt={currentFamilyProduct.name} onError={(event) => { event.currentTarget.onerror = null; event.currentTarget.src = cheesecakeCup; }} className="absolute inset-0 h-full w-full object-cover" style={{ animation: "familySlideIn 320ms ease-out" }} />
                    <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/45 to-transparent px-3 pb-2 pt-8 text-right">
                      <div aria-live="polite" className="truncate text-[12px] font-black text-white">{currentFamilyProduct.name}</div>
                      <div className="mt-0.5 text-[10px] font-bold text-[#E7CC94]">{currentFamilyProduct.price} د.إ</div>
                    </div>
                    <button type="button" aria-label="الصورة العائلية السابقة" onClick={() => moveFamilySlide(-1)} className="absolute right-2 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full border border-white/20 bg-black/45 text-xl text-white backdrop-blur transition hover:bg-black/70 focus:outline-none focus:ring-2 focus:ring-[#C9A86A]">‹</button>
                    <button type="button" aria-label="الصورة العائلية التالية" onClick={() => moveFamilySlide(1)} className="absolute left-2 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full border border-white/20 bg-black/45 text-xl text-white backdrop-blur transition hover:bg-black/70 focus:outline-none focus:ring-2 focus:ring-[#C9A86A]">›</button>
                  </div>
                  <div className="mt-2 flex items-center justify-center gap-2" role="group" aria-label="اختيار صورة من المنتجات العائلية">
                    {familyProducts.map((product, index) => <button key={product.slug} type="button" aria-label={`عرض ${product.name}`} aria-current={index === activeFamilySlide ? "true" : undefined} onClick={() => setActiveFamilySlide(index)} className={`h-2 rounded-full transition-all focus:outline-none focus:ring-2 focus:ring-[#C9A86A] ${index === activeFamilySlide ? "w-6 bg-[#C9A86A]" : "w-2 bg-white/35 hover:bg-white/70"}`} />)}
                  </div>
                </div>}

                <h2 className="mt-6 text-[20px] font-black text-white leading-tight">أهلاً بك في حكاية حلا</h2>
                <p className="mt-2 text-[13px] leading-6 text-white/60">من قلب فلسطين إلى مائدتك<br/>وصفات جداتنا، بطعم الأصالة</p>

                <div className="mt-7 w-full space-y-3 text-right">
                  <label htmlFor="login-phone" className="block text-[12px] font-bold text-white/80">رقم الجوال</label>
                  <input id="login-phone" dir="ltr" autoComplete="tel" inputMode="tel" value={loginPhone} onChange={(event) => { setLoginPhone(event.target.value); setPhoneLoginMessage(""); }} placeholder="+971 50 123 4567" className="w-full h-[48px] rounded-[14px] border border-white/15 bg-white/10 px-4 text-left text-white placeholder:text-white/35 outline-none focus:border-[#C9A86A] focus:ring-2 focus:ring-[#C9A86A]/20" />
                  <button type="button" onClick={handlePhoneLoginPreparation} className="w-full h-[48px] rounded-[14px] bg-gradient-to-r from-[#C9A86A] to-[#8A6A2E] text-[#1A0A05] font-black text-[14px] shadow-[0_8px_24px_rgba(0,0,0,0.25)] active:scale-[0.98] transition-transform">متابعة برقم الجوال</button>
                  <label htmlFor="verification-code" className="block pt-1 text-[12px] font-bold text-white/80">رمز التحقق</label>
                  <input id="verification-code" dir="ltr" autoComplete="one-time-code" inputMode="numeric" maxLength={6} value={verificationCode} onChange={(event) => setVerificationCode(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="• • • • • •" disabled className="w-full h-[48px] rounded-[14px] border border-white/10 bg-black/20 px-4 text-center tracking-[0.6em] text-white placeholder:text-white/25 disabled:cursor-not-allowed disabled:opacity-60" />
                  <p className="text-[10px] leading-4 text-white/45">خانة الرمز جاهزة، وستُفعّل عند ربط إرسال SMS.</p>
                  {phoneLoginMessage && <p role="status" className="rounded-xl border border-[#C9A86A]/20 bg-black/20 p-3 text-[11px] leading-5 text-[#F2DDAE]">{phoneLoginMessage}</p>}
                </div>

                <div className="mt-3 w-full">
                  <button onClick={continueAsGuest} className="w-full h-[44px] rounded-[14px] border border-[#C9A86A]/40 bg-white/10 text-white font-bold text-[13px] hover:bg-white/15 transition-colors">متابعة التصفح كضيف</button>
                </div>

                {isFirebaseConfigured && <div className="mt-5 w-full border-t border-white/10 pt-5 text-right">
                  <p className="mb-2 text-[11px] font-bold text-[#F2DDAE]">دخول الإدارة</p>
                  <input type="email" value={adminEmail} onChange={(event) => setAdminEmail(event.target.value)} placeholder="البريد الإلكتروني" autoComplete="username" className="mb-2 w-full h-[44px] rounded-[12px] border border-white/15 bg-white/10 px-3 text-left text-white placeholder:text-white/35 outline-none focus:border-[#C9A86A]" />
                  <input type="password" value={adminPassword} onChange={(event) => setAdminPassword(event.target.value)} placeholder="كلمة المرور" autoComplete="current-password" className="mb-2 w-full h-[44px] rounded-[12px] border border-white/15 bg-white/10 px-3 text-left text-white placeholder:text-white/35 outline-none focus:border-[#C9A86A]" />
                  <button type="button" onClick={handleAdminLogin} className="w-full h-[44px] rounded-[12px] border border-[#C9A86A]/60 text-[#F2DDAE] font-bold text-[12px]">دخول المشرف</button>
                </div>}

                <p className="mt-5 text-[11px] leading-5 text-white/35 text-center">بالمتابعة، توافق على شروط حكاية حلا الفلسطينية<br/><span className="text-[#C9A86A]/60">وصفات أصلية • إرسال الطلب عبر واتساب</span></p>
              </div>
            </div>

            <div className="mt-6 flex items-center gap-2 text-[11px] text-white/25">
              <span className="w-1.5 h-1.5 rounded-full bg-[#149954]" />
              <span>فلسطين • أصالة • جودة</span>
              <span className="w-1.5 h-1.5 rounded-full bg-[#C1272D]" />
            </div>
          </div>
        </div>
      )}

      {/* MAIN SCREEN */}
      {screen === "main" && (
        <div className="relative min-h-screen">
          {/* Header */}
          <header className="absolute inset-x-0 top-0 z-30 text-white">
            <div className="mx-auto max-w-[1280px] px-4 h-[64px] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-[#1A0A05]/45 backdrop-blur border border-[#C9A86A]/50 text-[#C9A86A] grid place-items-center font-black text-[19px]">ح</div>
                <div>
                  <div className="font-black text-[15px] leading-none text-white">حكاية حلا</div>
                  <div className="text-[10px] text-white/65 font-bold tracking-widest">HEKAYET HALA</div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {!user && <button onClick={() => setScreen("login")} className="px-3 py-1.5 rounded-full bg-[#1A0A05]/55 backdrop-blur border border-[#C9A86A]/50 text-white text-[11px] font-bold">تسجيل الدخول</button>}
                {!defaultWhatsappNumber && <span className="px-3 py-1.5 rounded-full bg-[#1A0A05]/45 backdrop-blur border border-white/20 text-white text-[11px] font-bold">كتالوج المنتجات</span>}
                {isAdmin && <button onClick={()=>setScreen("admin")} className="relative px-3 py-1.5 rounded-full bg-[#1A0A05]/45 backdrop-blur border border-white/20 text-white text-[12px] font-bold">إدارة الطلبات {orders.length>0 && <span className="absolute -top-1 -right-1 w-4 h-4 bg-[#C1272D] text-white text-[9px] rounded-full grid place-items-center">{orders.length}</span>}</button>}
                {defaultWhatsappNumber && <div className="relative">
                  <button onClick={()=>toast(`السلة: ${cartCount} منتجات - ${cartTotal} د.إ`)} className="px-3 py-1.5 rounded-full bg-[#1A0A05]/55 backdrop-blur border border-white/20 text-white text-[12px] font-bold">السلة • {cartCount}</button>
                </div>}
                {user && <div className="flex items-center gap-2">
                  <span className="hidden sm:block text-[12px] font-medium max-w-[100px] truncate">{user?.phoneNumber || user?.displayName || user?.email}</span>
                  <button onClick={handleLogout} className="w-8 h-8 rounded-full bg-[#1A0A05]/45 border border-white/20 grid place-items-center text-[12px]">⎋</button>
                </div>}
              </div>
            </div>
          </header>

          {/* Hero */}
          <section className="relative h-[100svh] min-h-[620px] overflow-hidden">
            <img src={heroBg} alt="حلويات حكاية حلا الفلسطينية" className="absolute inset-0 w-full h-full object-cover scale-[1.08]" style={{ objectPosition: "center 62%" }} />
            <div className="absolute inset-0 bg-gradient-to-b from-[#1A0A05]/45 via-[#1A0A05]/28 to-[#1A0A05]/45" />
            <div className="absolute inset-0 tatreez opacity-[0.12]" />
            <div className="relative z-10 h-full flex flex-col items-center justify-center text-center px-4 pt-16">
              <div className="px-3 py-1 rounded-full bg-white/10 border border-white/15 text-[#C9A86A] text-[11px] font-bold backdrop-blur">{siteContent.heroBadge}</div>
              <h1 className="mt-4 max-w-[760px] text-4xl font-black text-white drop-shadow-lg sm:text-6xl">{siteContent.heroTitle}</h1>
              <p className="mt-3 max-w-[620px] text-sm leading-7 text-white/85 sm:text-base">{siteContent.heroDescription}</p>
              <button onClick={()=>document.getElementById('products')?.scrollIntoView({behavior:'smooth'})} className="absolute bottom-3 sm:bottom-4 left-1/2 -translate-x-1/2 px-7 h-[48px] rounded-full bg-[#FFFBF5] text-[#1A0A05] font-bold text-[13px] shadow-[0_10px_30px_rgba(0,0,0,0.25)] transition-transform hover:scale-[1.03] active:scale-[0.97]">استكشف الأصناف</button>
            </div>
          </section>

          {/* Products */}
          <section id="products" className="mx-auto max-w-[1280px] px-4 pb-10">
            <div className="flex items-center justify-between">
              <h2 className="text-[18px] font-black">حلوياتنا الفلسطينية الأصيلة</h2>
              <span className="text-[11px] text-[#5E1C1C]/60">{products.length} أصناف • الطلب قريباً</span>
            </div>
            {catalogQuery.isError && <p role="status" className="mt-2 text-[11px] text-[#5E1C1C]/60">تعذر الاتصال بقاعدة البيانات؛ نعرض نسخة الكتالوج الاحتياطية.</p>}
            <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
              {products.map(p => {
                const inCart = cart.find(c=>c.id===p.id);
                return (
                  <div key={p.id} className="rounded-[18px] overflow-hidden bg-white border border-black/[0.04] shadow-[0_8px_24px_rgba(0,0,0,0.06)] hover:shadow-[0_16px_40px_rgba(0,0,0,0.12)] hover:-translate-y-1 transition-all group">
                    <div className="relative h-[160px] overflow-hidden bg-[#F5EFE6]">
                      <img src={p.image} alt={p.name} className="w-full h-full object-cover group-hover:scale-[1.05] transition-transform duration-500" />
                      <span className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-[#1A0A05]/80 text-white text-[10px] backdrop-blur">{p.tag}</span>
                    </div>
                    <div className="p-3">
                      <div className="font-bold text-[13px] leading-tight line-clamp-1">{p.name}</div>
                      <div className="mt-1 flex items-center justify-between">
                        <span className="text-[#C9A86A] font-black text-[13px]">{p.price} د.إ</span>
                        <span className="text-[10px] text-[#5E1C1C]/40">للتعرّف على الصنف</span>
                      </div>
                      <div className="mt-2.5 grid grid-cols-1 gap-1.5">
                        <button onClick={()=>setSelectedProduct(p)} className="h-[36px] rounded-[10px] border border-[#C9A86A]/30 text-[11px] font-bold">عرض التفاصيل</button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Cart summary */}
            {cart.length>0 && defaultWhatsappNumber && (
              <div className="mt-8 rounded-[20px] bg-white border border-[#C9A86A]/15 p-4 shadow-[0_8px_24px_rgba(0,0,0,0.06)]">
                <h3 className="font-black text-[14px]">سلة التسوق • {cartCount} منتجات</h3>
                <div className="mt-3 space-y-2">
                  {cart.map(c=>{
                    const p = products.find(pr=>pr.id===c.id);
                    if(!p) return null;
                    return (
                      <div key={c.id} className="flex items-center justify-between py-2 border-b border-black/5 last:border-0">
                        <div className="flex items-center gap-2">
                          <img src={p.image} className="w-10 h-10 rounded-lg object-cover" />
                          <div>
                            <div className="text-[12px] font-bold">{p.name}</div>
                            <div className="text-[11px] text-[#5E1C1C]/50">{p.price} د.إ</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button onClick={()=>updateQty(c.id, -1)} className="w-7 h-7 rounded-full bg-black/5 grid place-items-center">-</button>
                          <span className="text-[12px] font-bold w-4 text-center">{c.q}</span>
                          <button onClick={()=>updateQty(c.id, 1)} className="w-7 h-7 rounded-full bg-black/5 grid place-items-center">+</button>
                          <button onClick={()=>removeFromCart(c.id)} className="ml-2 text-[12px]">🗑️</button>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-4 grid sm:grid-cols-2 gap-2">
                  <input value={customerName} onChange={(e)=>setCustomerName(e.target.value)} placeholder="اسمك الكامل" autoComplete="name" className="px-3 py-2 rounded-xl border border-black/10 text-[12px]" />
                  <input value={customerPhone} onChange={(e)=>setCustomerPhone(e.target.value)} placeholder="رقم هاتفك للتواصل" autoComplete="tel" inputMode="tel" className="px-3 py-2 rounded-xl border border-black/10 text-[12px]" />
                  <textarea value={deliveryNote} onChange={(e)=>setDeliveryNote(e.target.value)} placeholder="عنوان التوصيل أو ملاحظات (اختياري)" className="sm:col-span-2 px-3 py-2 rounded-xl border border-black/10 text-[12px] resize-y min-h-[60px]" />
                </div>
                <div className="mt-4 flex items-center justify-between gap-3">
                  <span className="font-black">المجموع: {cartTotal} د.إ</span>
                  <div className="flex gap-2">
                    <button onClick={handleOrder} className={`px-4 h-[36px] rounded-full font-bold text-[12px] ${orderMethod==="whatsapp" ? "bg-[#25D366] text-white" : "bg-[#1A0A05] text-white"}`}>{orderMethod==="whatsapp" ? "إرسال واتساب" : "تأكيد الطلب"}</button>
                  </div>
                </div>
              </div>
            )}
          </section>

          <section className="mx-auto grid max-w-[1280px] gap-4 px-4 pb-10 sm:grid-cols-2">
            <article className="rounded-[20px] bg-white p-5 shadow-sm"><h2 className="text-lg font-black">{siteContent.aboutTitle}</h2><p className="mt-2 text-sm leading-7 text-[#5E1C1C]/70">{siteContent.aboutText}</p></article>
            <article className="rounded-[20px] bg-white p-5 shadow-sm"><h2 className="text-lg font-black">الأسئلة الشائعة</h2>{siteContent.faq.length ? <div className="mt-2 space-y-3">{siteContent.faq.map((item, index) => <details key={`${item.question}-${index}`} className="rounded-lg bg-[#FFFBF5] p-3"><summary className="cursor-pointer text-sm font-bold">{item.question}</summary><p className="mt-2 text-sm leading-6 text-[#5E1C1C]/70">{item.answer}</p></details>)}</div> : <p className="mt-2 text-sm text-[#5E1C1C]/60">يمكنكم التواصل معنا عبر واتساب لأي استفسار.</p>}</article>
            <article className="rounded-[20px] bg-white p-5 shadow-sm"><h2 className="text-lg font-black">التوصيل والاسترجاع والخصوصية</h2><p className="mt-2 text-sm leading-7 text-[#5E1C1C]/70"><b>التوصيل:</b> {siteContent.deliveryPolicy}</p><p className="mt-2 text-sm leading-7 text-[#5E1C1C]/70"><b>الاسترجاع:</b> {siteContent.returnPolicy}</p><p className="mt-2 text-sm leading-7 text-[#5E1C1C]/70"><b>الخصوصية:</b> {siteContent.privacyPolicy}</p></article>
            <article className="rounded-[20px] bg-white p-5 shadow-sm"><h2 className="text-lg font-black">تواصل معنا</h2><div className="mt-2 space-y-1 text-sm text-[#5E1C1C]/70">{siteContent.contactPhone && <p>الهاتف: {siteContent.contactPhone}</p>}{siteContent.contactEmail && <p>الإيميل: {siteContent.contactEmail}</p>}{siteContent.contactAddress && <p>العنوان: {siteContent.contactAddress}</p>}{!siteContent.contactPhone && !siteContent.contactEmail && !siteContent.contactAddress && <p>تواصلوا معنا عبر واتساب.</p>}</div></article>
          </section>

          {/* Toast */}
          {showToast && (
            <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2.5 rounded-full bg-[#1A0A05] text-white text-[12px] font-bold shadow-[0_12px_32px_rgba(0,0,0,0.3)] border border-[#C9A86A]/20">
              {showToast}
            </div>
          )}

          {/* Product Modal */}
          {selectedProduct && (
            <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
              <div className="absolute inset-0 bg-black/60 backdrop-blur-[10px]" onClick={()=>setSelectedProduct(null)} />
              <div className="relative w-full sm:max-w-[640px] bg-[#FFFBF5] rounded-t-[24px] sm:rounded-[20px] overflow-hidden max-h-[90vh] overflow-y-auto">
                <button onClick={()=>setSelectedProduct(null)} className="absolute top-3 left-3 w-8 h-8 rounded-full bg-white border border-black/10 grid place-items-center z-10">✕</button>
                <img src={selectedProduct.image} alt={selectedProduct.name} className="w-full h-[260px] object-cover" />
                <div className="p-5">
                  <div className="flex gap-2 mb-2">
                    <span className="px-2 py-1 rounded-full bg-[#1A0A05] text-white text-[10px]">{selectedProduct.tag}</span>
                    <span className="px-2 py-1 rounded-full bg-[#C9A86A]/15 text-[#8A6A2E] text-[10px] border border-[#C9A86A]/20">صناعة فلسطينية</span>
                  </div>
                  <h3 className="text-[20px] font-black">{selectedProduct.name}</h3>
                  <p className="mt-2 text-[13px] leading-6 text-[#5E1C1C]/70">{selectedProduct.desc}</p>
                  <div className="mt-4 p-3 rounded-[14px] bg-white border border-[#C9A86A]/10 flex items-center justify-between">
                    <span className="text-[12px] text-[#5E1C1C]/50">السعر</span>
                    <span className="font-black text-[18px] text-[#C9A86A]">{selectedProduct.price} د.إ</span>
                  </div>
                  {defaultWhatsappNumber ? <button onClick={()=>{addToCart(selectedProduct.id); setSelectedProduct(null);}} className="mt-4 w-full h-[44px] rounded-[12px] bg-[#1A0A05] text-white font-bold">أضف إلى السلة</button> : <div className="mt-4 w-full py-3 rounded-[12px] bg-[#1A0A05]/5 text-center text-[#5E1C1C]/70 font-bold text-[13px]">الطلب عبر الموقع سيتاح قريباً</div>}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ADMIN / Orders screen - لوحة إدارة الطلبات */}
      {screen === "admin" && isAdmin && (isFirebaseConfigured || isAdminPreview) && (
        <div className="min-h-screen bg-[#FFFBF5] p-4">
          {isAdminPreview && <div className="mx-auto mb-3 max-w-[1100px] rounded-xl border border-amber-300 bg-amber-50 p-3 text-center text-[12px] font-bold text-amber-900">وضع معاينة إداري محلي — لا توجد بيانات Firestore حقيقية في هذه المعاينة.</div>}
          <AdminPanel initialProducts={products} onClose={() => setScreen("main")} onSaved={() => catalogQuery.refetch()} />
          <div className="mx-auto max-w-[900px]">
            <div className="flex items-center justify-between">
              <h1 className="text-[20px] font-black">لوحة إدارة الطلبات {orderMethod==="whatsapp" ? "(واتساب)" : "(داخلي)"}</h1>
              <button onClick={()=>setScreen("main")} className="px-4 h-[36px] rounded-full bg-[#1A0A05] text-white text-[12px] font-bold">العودة للمتجر</button>
            </div>

            <div className="mt-4 p-3 rounded-[14px] bg-white border border-[#C9A86A]/15 flex flex-wrap gap-2 items-center">
              <span className="text-[12px] font-bold">طريقة استقبال الطلبات:</span>
              <button onClick={()=>setOrderMethod("whatsapp")} className={`px-3 py-1.5 rounded-full text-[11px] font-bold border ${orderMethod==="whatsapp" ? "bg-[#25D366] text-white border-[#25D366]" : "bg-white"}`}>واتساب - إرسال مباشر للعميل</button>
              <button onClick={()=>setOrderMethod("internal")} className={`px-3 py-1.5 rounded-full text-[11px] font-bold border ${orderMethod==="internal" ? "bg-[#1A0A05] text-white border-[#1A0A05]" : "bg-white"}`}>داخلي - لوحة تحكم</button>
            </div>

            <div className="mt-4 grid gap-3">
              {orders.length===0 ? <div className="p-8 text-center bg-white rounded-[14px] border border-dashed text-[13px] text-[#5E1C1C]/40">لا توجد طلبات بعد</div> :
                orders.map(o=>(
                  <div key={o.id} className="p-4 rounded-[14px] bg-white border border-[#C9A86A]/15 shadow-[0_4px_12px_rgba(0,0,0,0.04)]">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-black text-[13px]">{o.id} - {o.total} د.إ</div>
                        <div className="text-[11px] text-[#5E1C1C]/50">{new Date(o.date).toLocaleString("ar-AE")} - {o.userName} - {o.customerPhone || o.user}</div>
                      </div>
                      <span className="px-2 py-1 rounded-full bg-[#C9A86A]/15 text-[10px] font-bold">{o.status}</span>
                    </div>
                    <div className="mt-2 text-[12px] whitespace-pre-line bg-[#FFFBF5] p-2 rounded-lg border border-black/5">{o.details}</div>
                    {o.deliveryNote && <div className="mt-2 text-[12px] bg-[#FFFBF5] p-2 rounded-lg border border-black/5"><b>العنوان/الملاحظات:</b> {o.deliveryNote}</div>}
                    {orderMethod==="whatsapp" && (
                      <button onClick={()=>{
                        const msg = `تأكيد طلب ${o.id}\n${o.details}\nالمجموع: ${o.total} د.إ`;
                        window.open(`https://wa.me/${defaultWhatsappNumber}?text=${encodeURIComponent(msg)}`, "_blank", "noopener,noreferrer");
                      }} className="mt-2 px-3 h-[32px] rounded-full bg-[#25D366] text-white text-[11px] font-bold">إعادة إرسال واتساب</button>
                    )}
                    {isAdmin && orderMethod === "internal" && <div className="mt-3 flex items-center gap-2 text-[11px]">
                      <span className="font-bold">تحديث الحالة:</span>
                      {["جديد", "قيد التحضير", "تم التوصيل"].map((status) => <button key={status} onClick={()=>updateOrderStatus(o, status)} className="px-3 py-1 rounded-full border border-[#C9A86A]/30 hover:bg-[#C9A86A]/10">{status}</button>)}
                    </div>}
                  </div>
                ))
              }
            </div>

            <div className="mt-6 p-4 rounded-[14px] bg-[#1A0A05] text-white">
              <h3 className="font-bold text-[13px]">كيف تختار؟</h3>
              <p className="mt-2 text-[11px] leading-5 opacity-70">
                <b>واتساب:</b> أسهل وأسرع للبداية - الطلب يذهب مباشرة لرقمك في واتساب كرسالة جاهزة. لا تحتاج سيرفر. مناسب إذا أنت تدير الطلبات بنفسك.<br/>
                <b>داخلي:</b> احترافي - الطلبات تُحفظ في قاعدة بيانات (Firestore) ولوحة التحكم هذه. مناسب إذا عندك فريق توصيل وتريد تتبع الحالات. يحتاج إعداد Firebase.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
