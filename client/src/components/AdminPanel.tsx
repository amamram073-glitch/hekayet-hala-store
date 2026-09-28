import { useEffect, useMemo, useState } from "react";
import {
  addDoc,
  collection,
  deleteDoc,
  doc,
  onSnapshot,
  orderBy,
  query,
  setDoc,
  updateDoc,
} from "firebase/firestore";
import { getDownloadURL, ref, uploadBytes } from "firebase/storage";
import { db, storage, functions } from "../firebase";
import { httpsCallable } from "firebase/functions";
import SalesCharts from "./SalesCharts";

type Product = {
  id: number;
  slug: string;
  name: string;
  price: number;
  image: string;
  desc: string;
  tag: string;
  collection: "classic" | "family";
  stock?: number;
};

type Order = {
  id: string;
  total: number;
  status?: string;
  userName?: string;
  customerPhone?: string;
  details?: string;
  date?: string;
  items?: Array<{ name: string; quantity: number; unitPrice: number }>;
};

type Content = {
  heroTitle: string;
  heroDescription: string;
  heroBadge: string;
  aboutTitle: string;
  aboutText: string;
  faq: Array<{ question: string; answer: string }>;
  contactPhone: string;
  contactEmail: string;
  contactAddress: string;
  deliveryPolicy: string;
  returnPolicy: string;
  privacyPolicy: string;
};

type StaffMember = { uid: string; email: string; displayName: string; active: boolean; permissions: Record<string, boolean> };
const permissionOptions = [
  ["orders_read", "مشاهدة الطلبات"], ["orders_update", "تحديث حالات الطلبات"], ["inventory_read", "مشاهدة المخزون"], ["inventory_write", "تعديل المخزون"],
  ["products_write", "إدارة المنتجات"], ["content_write", "تعديل محتوى الموقع"], ["reports_read", "مشاهدة التقارير"], ["staff_manage", "إدارة الموظفين"],
] as const;

const defaultContent: Content = {
  heroTitle: "حلويات فلسطينية أصيلة",
  heroDescription: "من قلب فلسطين إلى مائدتك، وصفات جداتنا بطعم الأصالة.",
  heroBadge: "حلويات فلسطينية",
  aboutTitle: "حكاية حلا من فلسطين",
  aboutText: "نقدّم حلويات فلسطينية أصيلة بوصفات عائلية ومكونات مختارة.",
  faq: [],
  contactPhone: "",
  contactEmail: "",
  contactAddress: "",
  deliveryPolicy: "سيتم التنسيق معكم عبر واتساب.",
  returnPolicy: "يرجى التواصل معنا فورًا عند وجود أي مشكلة في الطلب.",
  privacyPolicy: "نستخدم بيانات التواصل لإتمام الطلب فقط.",
};

const demoOrders: Order[] = [
  { id: "DEMO-1001", total: 136, status: "تم التوصيل", userName: "سارة — عميل تجريبي", customerPhone: "+971500000001", date: "2026-09-27T10:00:00Z", details: "تشيز كيك x2 • معمول بالتمر x2", items: [{ name: "تشيز كيك", quantity: 2, unitPrice: 18 }, { name: "معمول بالتمر الفاخر", quantity: 2, unitPrice: 16 }] },
  { id: "DEMO-1002", total: 100, status: "قيد التحضير", userName: "محمد — عميل تجريبي", customerPhone: "+971500000002", date: "2026-09-28T08:30:00Z", details: "بوكس العائلة x1", items: [{ name: "بوكس العائلة", quantity: 1, unitPrice: 100 }] },
  { id: "DEMO-1003", total: 51, status: "جديد", userName: "ليان — عميل تجريبي", customerPhone: "+971500000003", date: "2026-09-28T09:15:00Z", details: "الحلبة الفلسطينية x1 • سينابون الفلسطيني x2", items: [{ name: "الحلبة الفلسطينية", quantity: 1, unitPrice: 17 }, { name: "سينابون الفلسطيني", quantity: 2, unitPrice: 19 }] },
];

export default function AdminPanel({
  initialProducts,
  onClose,
  onSaved,
  demoMode = false,
  isOwner = false,
  permissions = [],
}: {
  initialProducts: Product[];
  onClose: () => void;
  onSaved: () => void;
  demoMode?: boolean;
  isOwner?: boolean;
  permissions?: string[];
}) {
  const [products, setProducts] = useState<Product[]>(initialProducts);
  const [content, setContent] = useState<Content>(defaultContent);
  const [editing, setEditing] = useState<Product | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [message, setMessage] = useState("");
  const [uploading, setUploading] = useState(false);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [newStaff, setNewStaff] = useState({ email: "", password: "", displayName: "", permissions: { orders_read: true, inventory_read: true } as Record<string, boolean> });
  const can = (permission: string) => isOwner || permissions.includes(permission);
  const lowStockThreshold = 5;

  useEffect(() => {
    if (demoMode) {
      setOrders(demoOrders);
      return;
    }
    if (!db) return;
    const productsQuery = query(collection(db, "products"), orderBy("id", "asc"));
    const unsubscribeProducts = onSnapshot(productsQuery, (snapshot) => {
      if (snapshot.empty) return;
      setProducts(snapshot.docs.map((item) => ({ id: Number(item.data().id), ...item.data() } as Product)));
    });
    const unsubscribeContent = onSnapshot(doc(db, "siteContent", "main"), (snapshot) => {
      if (snapshot.exists()) setContent({ ...defaultContent, ...(snapshot.data() as Partial<Content>) });
    });
    const ordersQuery = query(collection(db, "orders"), orderBy("date", "desc"));
    const unsubscribeOrders = onSnapshot(ordersQuery, (snapshot) => {
      setOrders(snapshot.docs.map((item) => ({ ...item.data(), firestoreDocId: item.id } as unknown as Order)));
    });
    return () => { unsubscribeProducts(); unsubscribeContent(); unsubscribeOrders(); };
  }, [demoMode]);

  useEffect(() => {
    if (!isOwner || demoMode || !functions) return;
    httpsCallable(functions, "listStaff")()
      .then((result) => setStaff(result.data as StaffMember[]))
      .catch((error) => { console.error(error); persistMessage("تعذر تحميل الموظفين."); });
  }, [isOwner, demoMode]);

  const persistMessage = (text: string) => {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 3500);
  };

  const saveProduct = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (demoMode) { persistMessage("المعاينة للعرض فقط — لن يتم حفظ التعديل."); return; }
    if (!db || !editing) return;
    const cleanName = editing.name.trim().slice(0, 120);
    const cleanDescription = editing.desc.trim().slice(0, 1000);
    if (!cleanName || editing.price < 0 || !editing.slug.trim()) {
      persistMessage("تحقق من الاسم والسعر والمعرّف قبل الحفظ.");
      return;
    }
    const data = { ...editing, name: cleanName, desc: cleanDescription, slug: editing.slug.trim().toLowerCase().replace(/[^a-z0-9-]/g, "-") };
    try {
      await setDoc(doc(db, "products", String(data.id)), data, { merge: true });
      setEditing(null);
      persistMessage("تم حفظ المنتج.");
      onSaved();
    } catch (error) {
      console.error(error);
      persistMessage("تعذر حفظ المنتج. راجع قواعد Firestore.");
    }
  };

  const addProduct = () => {
    if (demoMode) { persistMessage("المعاينة للعرض فقط — إدارة المنتجات متاحة في حساب Admin الحقيقي."); return; }
    const nextId = Math.max(0, ...products.map((product) => product.id)) + 1;
    setEditing({ id: nextId, slug: `product-${nextId}`, name: "منتج جديد", price: 0, image: "", desc: "", tag: "جديد", collection: "classic" });
  };

  const removeProduct = async (product: Product) => {
    if (demoMode) { persistMessage("المعاينة للعرض فقط — لا يمكن حذف المنتجات."); return; }
    if (!db || !window.confirm(`حذف ${product.name}؟`)) return;
    try {
      await deleteDoc(doc(db, "products", String(product.id)));
      persistMessage("تم حذف المنتج.");
      onSaved();
    } catch (error) {
      console.error(error);
      persistMessage("تعذر حذف المنتج.");
    }
  };

  const uploadImage = async (file: File) => {
    if (demoMode) { persistMessage("المعاينة للعرض فقط — لا يمكن رفع الصور."); return; }
    if (!storage || !editing) return;
    if (!/^image\/(jpeg|png|webp|avif)$/.test(file.type) || file.size > 5 * 1024 * 1024) {
      persistMessage("الصورة يجب أن تكون JPG أو PNG أو WEBP وبحجم لا يتجاوز 5MB.");
      return;
    }
    setUploading(true);
    try {
      const storageRef = ref(storage, `products/${editing.id}-${crypto.randomUUID()}.${file.type.split("/")[1]}`);
      await uploadBytes(storageRef, file, { contentType: file.type });
      const url = await getDownloadURL(storageRef);
      setEditing({ ...editing, image: url });
      persistMessage("تم رفع الصورة، اضغط حفظ المنتج.");
    } catch (error) {
      console.error(error);
      persistMessage("تعذر رفع الصورة. تحقق من إعدادات Storage.");
    } finally {
      setUploading(false);
    }
  };

  const saveContent = async () => {
    if (demoMode) { persistMessage("المعاينة للعرض فقط — لن يتم حفظ المحتوى."); return; }
    if (!db) return;
    try {
      await setDoc(doc(db, "siteContent", "main"), {
        ...content,
        heroTitle: content.heroTitle.trim().slice(0, 160),
        heroDescription: content.heroDescription.trim().slice(0, 500),
        aboutText: content.aboutText.trim().slice(0, 3000),
      }, { merge: true });
      persistMessage("تم حفظ محتوى الموقع.");
    } catch (error) {
      console.error(error);
      persistMessage("تعذر حفظ المحتوى.");
    }
  };

  const faqText = useMemo(() => content.faq.map((item) => `${item.question}||${item.answer}`).join("\n"), [content.faq]);
  const report = useMemo(() => {
    const delivered = orders.filter((order) => order.status === "تم التوصيل");
    const revenue = delivered.reduce((sum, order) => sum + Number(order.total || 0), 0);
    const allRevenue = orders.reduce((sum, order) => sum + Number(order.total || 0), 0);
    const productSales = new Map<string, number>();
    orders.forEach((order) => order.items?.forEach((item) => productSales.set(item.name, (productSales.get(item.name) ?? 0) + Number(item.quantity || 0))));
    const topProducts = Array.from(productSales.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5);
    return { delivered: delivered.length, revenue, allRevenue, topProducts };
  }, [orders]);

  const changeOrderStatus = async (order: Order, status: string) => {
    if (demoMode) { persistMessage("المعاينة للعرض فقط — لن يتم تغيير حالة الطلب."); return; }
    if (!db || !(order as Order & { firestoreDocId?: string }).firestoreDocId) return;
    try {
      await updateDoc(doc(db, "orders", (order as Order & { firestoreDocId: string }).firestoreDocId), { status });
      persistMessage("تم تحديث حالة الطلب.");
    } catch (error) {
      console.error(error);
      persistMessage("تعذر تحديث حالة الطلب.");
    }
  };

  const getStock = (product: Product) => Number.isFinite(Number(product.stock)) ? Number(product.stock) : 20;

  const updateStock = async (product: Product, nextStock: number) => {
    const stock = Math.max(0, Math.floor(nextStock));
    if (demoMode) { persistMessage("المعاينة للعرض فقط — لن يتم حفظ كمية المخزون."); return; }
    if (!can("inventory_write")) { persistMessage("لا تملك صلاحية تعديل المخزون."); return; }
    if (!db) { persistMessage("إعداد Firebase غير مكتمل."); return; }
    try {
      await setDoc(doc(db, "products", String(product.id)), { stock }, { merge: true });
      setProducts((current) => current.map((item) => item.id === product.id ? { ...item, stock } : item));
      persistMessage(`تم تحديث مخزون ${product.name}.`);
    } catch (error) {
      console.error(error);
      persistMessage("تعذر تحديث المخزون. تحقق من صلاحيات Admin.");
    }
  };

  const newOrdersCount = orders.filter((order) => (order.status || "جديد") === "جديد").length;

  const createStaff = async () => {
    if (!functions || !newStaff.email || newStaff.password.length < 8 || !newStaff.displayName.trim()) { persistMessage("أدخل اسم الموظف والبريد وكلمة مرور من 8 أحرف على الأقل."); return; }
    try {
      await httpsCallable(functions, "createStaffUser")(newStaff);
      const result = await httpsCallable(functions, "listStaff")();
      setStaff(result.data as StaffMember[]);
      setNewStaff({ email: "", password: "", displayName: "", permissions: { orders_read: true, inventory_read: true } });
      persistMessage("تم إنشاء حساب الموظف وصلاحياته.");
    } catch (error) { console.error(error); persistMessage("تعذر إنشاء الموظف. تحقق من صلاحية المسؤول ومن أن البريد غير مستخدم."); }
  };

  const updateStaff = async (member: StaffMember, patch: Partial<StaffMember>) => {
    if (!functions) return;
    const next = { ...member, ...patch };
    try { await httpsCallable(functions, "updateStaffUser")({ uid: member.uid, displayName: next.displayName, active: next.active, permissions: next.permissions }); setStaff((current) => current.map((item) => item.uid === member.uid ? next : item)); persistMessage("تم تحديث الموظف."); }
    catch (error) { console.error(error); persistMessage("تعذر تحديث صلاحيات الموظف."); }
  };

  const deleteStaff = async (member: StaffMember) => {
    if (!functions || !window.confirm(`حذف حساب ${member.displayName}؟`)) return;
    try { await httpsCallable(functions, "deleteStaffUser")({ uid: member.uid }); setStaff((current) => current.filter((item) => item.uid !== member.uid)); persistMessage("تم حذف حساب الموظف."); }
    catch (error) { console.error(error); persistMessage("تعذر حذف حساب الموظف."); }
  };

  return (
    <div className="min-h-screen bg-[#FFFBF5] p-4" dir="rtl">
      <div className="mx-auto max-w-[1100px]">
        <div className="flex items-center justify-between gap-3">
          <div><h1 className="text-[22px] font-black">لوحة تحكم حكاية حلا</h1><p className="mt-1 text-[12px] text-[#5E1C1C]/60">{demoMode ? "معاينة للعرض فقط — البيانات تجريبية." : "التعديلات تُحفظ في Firestore وتظهر لجميع الزوار."}</p></div>
          <button onClick={onClose} className="rounded-full bg-[#1A0A05] px-4 py-2 text-[12px] font-bold text-white">العودة للمتجر</button>
        </div>
        {message && <div role="status" className="mt-4 rounded-xl border border-[#C9A86A]/30 bg-[#C9A86A]/10 p-3 text-[12px] font-bold">{message}</div>}

        <section className="mt-5 rounded-2xl bg-[#1A0A05] p-4 text-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-black">التقارير وتتبع الطلبات</h2><span className="text-[11px] text-white/60">الأرقام من الطلبات الداخلية المحفوظة</span></div>
          {newOrdersCount > 0 && <div className="mt-3 rounded-xl border border-[#F2DDAE]/40 bg-[#C9A86A]/20 p-3 text-[12px] font-bold text-[#F2DDAE]">لديك {newOrdersCount} طلبات جديدة تحتاج المتابعة. يتم تحديث القائمة مباشرة من Firestore.</div>}
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className="rounded-xl bg-white/10 p-3"><div className="text-[11px] text-white/60">كل الطلبات</div><div className="mt-1 text-xl font-black">{orders.length}</div></div>
            <div className="rounded-xl bg-white/10 p-3"><div className="text-[11px] text-white/60">قيد المتابعة</div><div className="mt-1 text-xl font-black">{orders.filter((order) => order.status !== "تم التوصيل").length}</div></div>
            <div className="rounded-xl bg-white/10 p-3"><div className="text-[11px] text-white/60">طلبات مكتملة</div><div className="mt-1 text-xl font-black">{report.delivered}</div></div>
            <div className="rounded-xl bg-[#C9A86A]/25 p-3"><div className="text-[11px] text-[#F2DDAE]">المبيعات المؤكدة</div><div className="mt-1 text-xl font-black text-[#F2DDAE]">{report.revenue} د.إ</div></div>
          </div>
          <div className="mt-3 text-[11px] text-white/60">قيمة كل الطلبات المسجلة: {report.allRevenue} د.إ</div>
          {report.topProducts.length > 0 && <div className="mt-4 rounded-xl bg-white/10 p-3"><h3 className="text-[12px] font-bold">الأكثر طلبًا</h3><div className="mt-2 grid gap-1 text-[11px] text-white/75">{report.topProducts.map(([name, quantity]) => <div key={name} className="flex justify-between"><span>{name}</span><span>{quantity} قطعة</span></div>)}</div></div>}
          <SalesCharts orders={orders} />
          <div className="mt-4 grid gap-2">{orders.slice(0, 12).map((order) => <div key={(order as Order & { firestoreDocId?: string }).firestoreDocId ?? order.id} className={`rounded-xl bg-white p-3 text-[#1A0A05] ${order.status === "جديد" ? "ring-2 ring-[#C9A86A]/50" : ""}`}><div className="flex flex-wrap items-center justify-between gap-2"><div><div className="font-bold">{order.id} • {order.total} د.إ {order.status === "جديد" && <span className="mr-2 rounded-full bg-[#C9A86A]/20 px-2 py-1 text-[10px]">جديد</span>}</div><div className="text-[11px] text-[#5E1C1C]/60">{order.userName || "عميل"} {order.customerPhone ? `• ${order.customerPhone}` : ""}</div></div><select disabled={!can("orders_update")} value={order.status || "جديد"} onChange={(event) => changeOrderStatus(order, event.target.value)} className="rounded-full border border-[#C9A86A]/40 px-2 py-1 text-[11px] font-bold disabled:opacity-50"><option>جديد</option><option>قيد التحضير</option><option>تم التوصيل</option><option>ملغى</option></select></div><div className="mt-2 text-[11px] text-[#5E1C1C]/65">{order.details || "تفاصيل الطلب غير متاحة"}</div></div>)}</div>
        </section>

        <section className="mt-5 rounded-2xl bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="font-black">إدارة المخزون</h2><p className="mt-1 text-[11px] text-[#5E1C1C]/60">حدّث الكمية المتاحة لكل منتج. يظهر تنبيه عند انخفاضها إلى {lowStockThreshold} أو أقل.</p></div><span className="rounded-full bg-[#C9A86A]/15 px-3 py-1 text-[11px] font-bold">{products.filter((product) => getStock(product) <= lowStockThreshold).length} منخفض المخزون</span></div>
          <div className="mt-4 grid gap-2">{products.map((product) => { const stock = getStock(product); return <div key={`stock-${product.id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-black/5 p-3"><div><div className="font-bold">{product.name}</div><div className={`text-[11px] ${stock <= lowStockThreshold ? "font-bold text-red-700" : "text-[#5E1C1C]/60"}`}>{stock <= lowStockThreshold ? "مخزون منخفض" : "متوفر"}</div></div><div className="flex items-center gap-2"><input aria-label={`كمية مخزون ${product.name}`} type="number" min="0" defaultValue={stock} onBlur={(event) => updateStock(product, Number(event.target.value))} disabled={demoMode || !can("inventory_write")} className="w-20 rounded-lg border border-[#C9A86A]/40 p-2 text-center text-sm font-bold disabled:opacity-50" /><span className="text-[11px]">قطعة</span></div></div>; })}</div>
        </section>

        <section className="mt-5 rounded-2xl bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between"><h2 className="font-black">المنتجات</h2><button disabled={demoMode || !can("products_write")} onClick={addProduct} className="rounded-full bg-[#1A0A05] px-4 py-2 text-[12px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">+ إضافة منتج</button></div>
          <div className="mt-3 grid gap-2">{products.map((product) => <div key={product.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-black/5 p-3"><div className="flex items-center gap-3"><img src={product.image} alt="" className="h-12 w-12 rounded-lg object-cover" /><div><div className="font-bold">{product.name}</div><div className="text-[11px] text-[#C9A86A]">{product.price} د.إ • {product.tag}</div></div></div><div className="flex gap-2"><button onClick={() => setEditing(product)} className="rounded-full border border-[#C9A86A]/40 px-3 py-1 text-[11px] font-bold">تعديل</button><button onClick={() => removeProduct(product)} className="rounded-full border border-red-200 px-3 py-1 text-[11px] font-bold text-red-700">حذف</button></div></div>)}</div>
        </section>

        {editing && <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"><form onSubmit={saveProduct} className="max-h-[90vh] w-full max-w-[620px] overflow-y-auto rounded-2xl bg-[#FFFBF5] p-5"><div className="flex justify-between"><h2 className="font-black">تعديل المنتج</h2><button type="button" onClick={() => setEditing(null)}>✕</button></div><div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="text-[12px] font-bold">الاسم<input required value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold">السعر<input required min="0" type="number" value={editing.price} onChange={(e) => setEditing({ ...editing, price: Number(e.target.value) })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold">المعرّف<input required value={editing.slug} onChange={(e) => setEditing({ ...editing, slug: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold">التصنيف<select value={editing.collection} onChange={(e) => setEditing({ ...editing, collection: e.target.value as Product["collection"] })} className="mt-1 w-full rounded-lg border p-2"><option value="classic">كلاسيكي</option><option value="family">عائلي</option></select></label></div><label className="mt-3 block text-[12px] font-bold">الشارة<input value={editing.tag} onChange={(e) => setEditing({ ...editing, tag: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="mt-3 block text-[12px] font-bold">الوصف<textarea value={editing.desc} onChange={(e) => setEditing({ ...editing, desc: e.target.value })} className="mt-1 min-h-24 w-full rounded-lg border p-2" /></label><label className="mt-3 block text-[12px] font-bold">صورة المنتج<input type="file" accept="image/jpeg,image/png,image/webp,image/avif" disabled={uploading} onChange={(e) => e.target.files?.[0] && uploadImage(e.target.files[0])} className="mt-1 w-full rounded-lg border p-2" /></label>{editing.image && <img src={editing.image} alt="معاينة" className="mt-3 h-40 w-full rounded-xl object-cover" />}<button disabled={uploading} className="mt-4 w-full rounded-xl bg-[#1A0A05] py-3 font-bold text-white">{uploading ? "جارٍ رفع الصورة..." : "حفظ المنتج"}</button></form></div>}

        {isOwner && !demoMode && <section className="mt-5 rounded-2xl bg-white p-4 shadow-sm">
          <h2 className="font-black">إدارة الموظفين والصلاحيات</h2>
          <p className="mt-1 text-[11px] text-[#5E1C1C]/60">المسؤول الرئيس فقط يستطيع إنشاء الحسابات وتعطيلها وحذفها وتعديل صلاحياتها.</p>
          <div className="mt-4 grid gap-2 rounded-xl bg-[#FFFBF5] p-3 sm:grid-cols-3">
            <input value={newStaff.displayName} onChange={(event) => setNewStaff({ ...newStaff, displayName: event.target.value })} placeholder="اسم الموظف" className="rounded-lg border p-2 text-[12px]" />
            <input value={newStaff.email} onChange={(event) => setNewStaff({ ...newStaff, email: event.target.value })} placeholder="البريد الإلكتروني" type="email" className="rounded-lg border p-2 text-[12px]" />
            <input value={newStaff.password} onChange={(event) => setNewStaff({ ...newStaff, password: event.target.value })} placeholder="كلمة مرور مؤقتة" type="password" className="rounded-lg border p-2 text-[12px]" />
            <div className="flex flex-wrap gap-2 sm:col-span-2">{permissionOptions.map(([key, label]) => <label key={key} className="flex items-center gap-1 text-[11px]"><input type="checkbox" checked={newStaff.permissions[key] === true} onChange={(event) => setNewStaff({ ...newStaff, permissions: { ...newStaff.permissions, [key]: event.target.checked } })} />{label}</label>)}</div>
            <button onClick={createStaff} className="rounded-lg bg-[#1A0A05] px-3 py-2 text-[12px] font-bold text-white">+ إضافة موظف حقيقي</button>
          </div>
          <div className="mt-4 grid gap-3">{staff.map((member) => <div key={member.uid} className="rounded-xl border border-black/5 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><div><div className="font-bold">{member.displayName}</div><div className="text-[11px] text-[#5E1C1C]/60">{member.email}</div></div><div className="flex gap-2"><button onClick={() => updateStaff(member, { active: !member.active })} className={`rounded-full px-3 py-1 text-[11px] font-bold ${member.active ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}>{member.active ? "مفعّل" : "معطّل"}</button><button onClick={() => deleteStaff(member)} className="rounded-full border border-red-200 px-3 py-1 text-[11px] font-bold text-red-700">حذف</button></div></div><div className="mt-3 flex flex-wrap gap-2">{permissionOptions.map(([key, label]) => <label key={key} className="flex items-center gap-1 text-[11px]"><input type="checkbox" checked={member.permissions?.[key] === true} onChange={(event) => updateStaff(member, { permissions: { ...member.permissions, [key]: event.target.checked } })} />{label}</label>)}</div></div>)}</div>
        </section>}

        <section className="mt-5 rounded-2xl bg-white p-4 shadow-sm"><h2 className="font-black">محتوى الصفحة الرئيسية والسياسات والتواصل</h2><div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-[12px] font-bold">الشارة<input value={content.heroBadge} onChange={(e) => setContent({ ...content, heroBadge: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold">العنوان الرئيسي<input value={content.heroTitle} onChange={(e) => setContent({ ...content, heroTitle: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold sm:col-span-2">الوصف<textarea value={content.heroDescription} onChange={(e) => setContent({ ...content, heroDescription: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold">عنوان من نحن<input value={content.aboutTitle} onChange={(e) => setContent({ ...content, aboutTitle: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold">الهاتف<input value={content.contactPhone} onChange={(e) => setContent({ ...content, contactPhone: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold sm:col-span-2">نص من نحن<textarea value={content.aboutText} onChange={(e) => setContent({ ...content, aboutText: e.target.value })} className="mt-1 w-full min-h-24 rounded-lg border p-2" /></label><label className="text-[12px] font-bold">الإيميل<input type="email" value={content.contactEmail} onChange={(e) => setContent({ ...content, contactEmail: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold">العنوان<input value={content.contactAddress} onChange={(e) => setContent({ ...content, contactAddress: e.target.value })} className="mt-1 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold">سياسة التوصيل<textarea value={content.deliveryPolicy} onChange={(e) => setContent({ ...content, deliveryPolicy: e.target.value })} className="mt-1 min-h-24 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold">سياسة الاسترجاع<textarea value={content.returnPolicy} onChange={(e) => setContent({ ...content, returnPolicy: e.target.value })} className="mt-1 min-h-24 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold sm:col-span-2">سياسة الخصوصية<textarea value={content.privacyPolicy} onChange={(e) => setContent({ ...content, privacyPolicy: e.target.value })} className="mt-1 min-h-24 w-full rounded-lg border p-2" /></label><label className="text-[12px] font-bold sm:col-span-2">الأسئلة الشائعة (كل سطر: السؤال||الجواب)<textarea value={faqText} onChange={(e) => setContent({ ...content, faq: e.target.value.split("\n").filter(Boolean).map((line) => { const [question, ...answer] = line.split("||"); return { question, answer: answer.join("||") }; }) })} className="mt-1 min-h-24 w-full rounded-lg border p-2" /></label></div><button onClick={saveContent} className="mt-4 w-full rounded-xl bg-[#1A0A05] py-3 font-bold text-white">حفظ محتوى الموقع</button></section>
      </div>
    </div>
  );
}
