import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Order = {
  total: number;
  status?: string;
  date?: string;
  items?: Array<{ name: string; quantity: number }>;
};

const chartColors = ["#C9A86A", "#8A6A2E", "#C1272D", "#149954", "#5E1C1C"];

export default function SalesCharts({ orders }: { orders: Order[] }) {
  const [view, setView] = useState<"sales" | "products">("sales");
  const data = useMemo(() => {
    const salesByDay = new Map<string, number>();
    const products = new Map<string, number>();
    orders.forEach((order) => {
      if (order.status !== "ملغى") {
        const day = order.date ? new Date(order.date).toLocaleDateString("ar-AE", { month: "short", day: "numeric" }) : "غير معروف";
        salesByDay.set(day, (salesByDay.get(day) ?? 0) + Number(order.total || 0));
      }
      order.items?.forEach((item) => products.set(item.name, (products.get(item.name) ?? 0) + Number(item.quantity || 0)));
    });
    return {
      sales: Array.from(salesByDay, ([day, amount]) => ({ day, amount })).slice(-14),
      products: Array.from(products, ([name, quantity]) => ({ name: name.length > 16 ? `${name.slice(0, 16)}…` : name, quantity })).sort((a, b) => b.quantity - a.quantity).slice(0, 8),
    };
  }, [orders]);

  const tooltipStyle = { backgroundColor: "#1A0A05", border: "1px solid rgba(201,168,106,.35)", borderRadius: 12, color: "#fff", direction: "rtl" as const };

  return (
    <div className="mt-4 rounded-xl bg-white/10 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[12px] font-bold">التحليل المرئي</h3>
        <div className="flex rounded-full bg-black/20 p-1 text-[11px]">
          <button onClick={() => setView("sales")} className={`rounded-full px-3 py-1 ${view === "sales" ? "bg-[#C9A86A] text-[#1A0A05]" : "text-white/70"}`}>المبيعات اليومية</button>
          <button onClick={() => setView("products")} className={`rounded-full px-3 py-1 ${view === "products" ? "bg-[#C9A86A] text-[#1A0A05]" : "text-white/70"}`}>الأكثر طلبًا</button>
        </div>
      </div>
      <div className="mt-3 h-[260px] w-full" dir="ltr">
        {view === "sales" ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.sales} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.12)" />
              <XAxis dataKey="day" tick={{ fill: "rgba(255,255,255,.65)", fontSize: 10 }} />
              <YAxis tick={{ fill: "rgba(255,255,255,.65)", fontSize: 10 }} width={42} />
              <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => [`${value} د.إ`, "المبيعات"]} />
              <Line type="monotone" dataKey="amount" stroke="#F2DDAE" strokeWidth={3} dot={{ r: 4, fill: "#C9A86A" }} activeDot={{ r: 7 }} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.products} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.12)" />
              <XAxis type="number" allowDecimals={false} tick={{ fill: "rgba(255,255,255,.65)", fontSize: 10 }} />
              <YAxis type="category" dataKey="name" width={105} tick={{ fill: "rgba(255,255,255,.75)", fontSize: 10 }} />
              <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => [`${value} قطعة`, "الكمية"]} />
              <Bar dataKey="quantity" radius={[0, 8, 8, 0]}>
                {data.products.map((_, index) => <Cell key={index} fill={chartColors[index % chartColors.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
      {!data.sales.length && !data.products.length && <p className="text-center text-[11px] text-white/60">ستظهر الرسوم بعد وصول أول طلب.</p>}
    </div>
  );
}
