# تقرير نقل حكاية حلا إلى Supabase

## نتيجة اختبار الاتصال

تم اختبار المشروع العام:

- Project URL: `https://nkagrazdklltmqpoysgm.supabase.co`
- Publishable key: يعمل ويعيد استجابة HTTP 200 من Supabase Auth.
- Email Authentication: مفعّل في المشروع.
- Phone Authentication: غير مفعّل حاليًا، وSupabase يذكر أن مزود SMS هو Twilio.
- جدول `public.products`: غير موجود حاليًا؛ أعاد PostgREST الخطأ `PGRST205`. هذا يؤكد أن الاتصال صحيح وأن المخطط لم يُنفذ بعد.

## تنفيذ المخطط

افتح Supabase Dashboard ثم **SQL Editor → New query**، الصق الملف `supabase/schema.sql` كاملًا، ثم اضغط **Run**.

المخطط ينشئ:

- `staff_members` للأدوار والصلاحيات.
- `products` مع `stock` وإدارة الصور.
- `site_content` للمحتوى والسياسات.
- `orders` مع العناصر والحالات والمبالغ.
- RLS Policies للتحقق من كل عملية من الخادم.
- Bucket باسم `product-images`.
- Realtime للمنتجات والطلبات والموظفين.

## إنشاء Admin الرئيس

بعد إنشاء حسابك في **Authentication → Users**، انسخ UID ونفّذ في SQL Editor، بعد استبدال القيمة:

```sql
insert into public.staff_members (id, email, display_name, role, active, permissions)
values ('USER_UUID', 'your-email@example.com', 'Admin الرئيس', 'owner', true, '{}'::jsonb)
on conflict (id) do update set role = 'owner', active = true;
```

لا يمكن إنشاء مستخدم Auth أو Admin الرئيس من المفتاح العام للواجهة؛ هذه العملية يجب أن تتم من لوحة Supabase أو Edge Function إدارية.

## تفعيل الجوال

من **Authentication → Providers → Phone**:

1. فعّل Phone.
2. اربط Twilio.
3. أضف بيانات Twilio داخل إعدادات Supabase السرية فقط.
4. اختبر رقمًا بصيغة دولية.

## الأمان

- المفتاح `sb_publishable_...` مخصص للواجهة ولا يمنح صلاحية إدارية.
- المفتاح `sb_secret_...` الذي أُرسل في المحادثة يجب تدويره فورًا ولا يجب استخدامه أو حفظه في GitHub.
- لا تستخدم `service_role` أو `sb_secret` في React أو متغير يبدأ بـ `VITE_`.
- كل عمليات الموظفين الحساسة يجب أن تتم عبر Edge Function أو لوحة Supabase، مع التحقق من `is_owner()`.
