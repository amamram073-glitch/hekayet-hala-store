# إعداد لوحة إدارة حكاية حلا

## ما تم تنفيذه

- السلة موجودة وتعمل محليًا في المتصفح.
- إرسال الطلب عبر واتساب مع الاسم والهاتف والملاحظات وتفاصيل المنتجات.
- دخول المستخدم عبر Firebase Authentication بخيارين: رقم الجوال عبر SMS أو البريد الإلكتروني وكلمة المرور.
- صلاحية المشرف منفصلة عن طريقة الدخول، ولا تُمنح إلا عبر مستند `admins/{uid}`.
- لوحة الإدارة من داخل التطبيق لإضافة وتعديل وحذف المنتجات.
- رفع صور المنتجات مباشرة إلى Firebase Storage مع السماح بصور JPG/PNG/WEBP/AVIF فقط وبحد أقصى 5MB.
- تعديل العنوان والوصف والشارة ومحتوى «من نحن» والأسئلة الشائعة والسياسات وبيانات التواصل.
- حفظ المنتجات والمحتوى في Firestore ليظهرا لجميع الزوار من أي جهاز.
- إرسال إشعار واتساب تلقائي عند تغيير حالة الطلب عبر Firebase Function وTwilio WhatsApp API.
- إدارة المخزون من لوحة المسؤول مع تنبيه عند انخفاض الكمية، وتحديث مباشر للطلبات الجديدة عبر Firestore.
- إدارة موظفين حقيقيين من لوحة Admin الرئيس: إنشاء الحساب، تعطيله، حذفه، وتعديل صلاحياته.

## الإعداد اليدوي المطلوب

1. أنشئ مشروع Firebase أو استخدم مشروعك الحالي.
2. فعّل **Authentication → Email/Password** و**Phone**. أضف نطاق الموقع إلى Authorized domains، وأكمل إعداد reCAPTCHA المطلوب لمصادقة الجوال.
3. فعّل **Cloud Firestore** و**Storage**.
4. أنشئ مستخدمًا إداريًا من Firebase Authentication، ثم أنشئ مستندًا في:

   `admins/{UID}`

   حيث `{UID}` هو UID للمستخدم الإداري. يمكن أن يكون محتوى المستند `{ "role": "admin" }`.

5. طبّق ملفي `firestore.rules` و`storage.rules` في Firebase Console.
6. أضف متغيرات البيئة للواجهة:

   ```env
   VITE_FIREBASE_API_KEY=...
   VITE_FIREBASE_AUTH_DOMAIN=...
   VITE_FIREBASE_PROJECT_ID=...
   VITE_FIREBASE_STORAGE_BUCKET=...
   VITE_FIREBASE_MESSAGING_SENDER_ID=...
   VITE_FIREBASE_APP_ID=...
   VITE_WHATSAPP_NUMBER=9715XXXXXXXX
   ```

7. سجّل نطاق الموقع المنشور في Firebase Authentication ضمن **Authorized domains**.
8. يجب أن يكون الموقع المنشور عبر HTTPS؛ الاستضافة الحالية توفر ذلك في الإنتاج.

## إعداد إشعارات Twilio WhatsApp

1. أنشئ حساب Twilio وفعّل WhatsApp Sender أو Sandbox للاختبار.
2. أنشئ قالب رسالة Utility معتمدًا إذا كان الإشعار قد يُرسل خارج نافذة محادثة العميل. المتغيرات المستخدمة هي:
   - `1`: رقم الطلب.
   - `2`: الحالة الجديدة.
   - `3`: الإجمالي.
3. من مجلد المشروع ثبّت اعتماديات الوظائف ثم أنشئ أسرار Firebase:

   ```bash
   cd functions
   npm install
   cd ..
   firebase functions:secrets:set TWILIO_ACCOUNT_SID
   firebase functions:secrets:set TWILIO_AUTH_TOKEN
   firebase functions:secrets:set TWILIO_WHATSAPP_FROM
   firebase functions:secrets:set TWILIO_CONTENT_SID
   firebase deploy --only functions:notifyOrderStatus
   ```

   عند طلب القيم، أدخلها في الطرفية فقط ولا تضعها في GitHub. قيمة `TWILIO_WHATSAPP_FROM` تكون رقم واتساب بصيغة دولية، مثل `+14155238886`.

4. بعد النشر، يؤدي تغيير `status` في مستند `orders` إلى تشغيل الوظيفة وإرسال الرسالة إلى `customerPhone`.

في بيئة الاختبار، يجب أن يوافق العميل على رسالة Twilio Sandbox. وفي الإنتاج يجب استخدام رسالة Utility معتمدة والالتزام بموافقة العميل وقواعد WhatsApp Business.

## ربط تسجيل الدخول وصلاحية Admin بشكل دائم

1. في Firebase Console افتح **Authentication → Sign-in method**، وفعّل **Email/Password** و**Phone**.
2. أضف نطاق الموقع إلى **Authorized domains**:

   ```text
   amamram073-glitch.github.io
   ```

3. أنشئ حساب الموظف أو المسؤول من شاشة الموقع. تسجيل Gmail هنا يعني بريد Gmail مع كلمة مرور Firebase.
4. لحساب Admin، افتح **Authentication → Users** وانسخ UID.
5. في Firestore أنشئ مستندًا بالمسار التالي:

   ```text
   admins/{UID}
   ```

   وضع داخله:

   ```json
   { "role": "admin" }
   ```

   لا تضع كلمة المرور في Firestore، ولا تضف UID الموظف إلى مجموعة `admins`.
6. قواعد `firestore.rules` تمنح كل عملية حسب صلاحية الموظف، بينما يبقى إنشاء وحذف حسابات الموظفين متاحًا فقط لـ Admin الرئيس عبر Firebase Functions. الصلاحية تستمر عبر الجلسات والأجهزة حتى تعطل الموظف أو تحذف حسابه.

## الموظفون الحقيقيون والصلاحيات المخصصة

بعد نشر وظائف Firebase، افتح لوحة Admin الرئيس وستظهر صفحة **إدارة الموظفين والصلاحيات**. أدخل اسم الموظف وبريده وكلمة مرور مؤقتة، ثم اختر الصلاحيات المطلوبة. يتم إنشاء مستخدم Firebase حقيقي ومستند `staff/{UID}` تلقائيًا.

الصلاحيات المتاحة:

```text
orders_read       مشاهدة الطلبات
orders_update     تحديث حالات الطلبات
inventory_read    مشاهدة المخزون
inventory_write   تعديل المخزون
products_write    إدارة المنتجات
content_write     تعديل محتوى الموقع
reports_read      مشاهدة التقارير
staff_manage      صلاحية إدارة الموظفين (لا تمنح إنشاء الحسابات؛ ذلك محصور بالـ Admin الرئيس)
```

لن يستطيع الموظف الوصول إلى لوحة الموقع إلا إذا كان حسابه نشطًا، ولن تنجح الكتابة حتى لو حاول استدعاء Firestore مباشرة دون الصلاحية المناسبة.

### نشر وظائف الموظفين والقواعد

يجب تنفيذ هذه الخطوة مرة واحدة من جهاز فيه Firebase CLI وحسابك مسجل الدخول:

```bash
firebase login
firebase use YOUR_FIREBASE_PROJECT_ID
firebase deploy --only functions,firestore:rules
```

يشمل النشر الوظائف التالية:

```text
listStaff
createStaffUser
updateStaffUser
deleteStaffUser
```

وظائف إنشاء وتعديل وحذف الحسابات تتحقق من وجود `admins/{UID}` في الخادم، لذلك لا يمكن للموظف منح نفسه صلاحيات أو حذف Admin الرئيس.

## المخزون والطلبات الجديدة

- قسم **إدارة المخزون** داخل لوحة المسؤول يقرأ كمية `stock` من مستند المنتج.
- عند عدم وجود قيمة سابقة، تعرض الواجهة كمية ابتدائية افتراضية قدرها 20 قطعة؛ احفظ كمية صحيحة لتثبيتها في Firestore.
- الكمية 5 أو أقل تظهر كـ **مخزون منخفض**.
- الطلبات الداخلية تُراقب عبر `onSnapshot`، وتظهر الطلبات ذات الحالة `جديد` مع تنبيه فوري.
- وضع `?admin=preview` يستخدم بيانات تجريبية فقط ولا يحفظ أي تغيير.

## الدخول

من شاشة الدخول اضغط **دخول المشرف**، ثم استخدم بريد وكلمة مرور مستخدم Firebase الذي أُنشئ له مستند في مجموعة `admins`.

لا توجد كلمة مرور ثابتة داخل الكود، ولا تضع مفاتيح Firebase أو أسرارًا خادمية في GitHub. قيم Firebase العامة للواجهة ليست أسرارًا؛ مفاتيح الخادم السرية لا تُضاف إلى `VITE_*`.

## ملاحظات

- المسار الحالي المؤكد للدفع هو **واتساب** كما طلبت. لم تتم إضافة دفع Visa/Mastercard/Apple Pay بعد اختيارك هذا المسار.
- أسماء المنتجات النهائية من ملف Connect لم تصل بعد؛ الكتالوج الحالي يبقى كما هو إلى أن يصل الملف.
- يجب ضبط رقم واتساب بصيغة دولية رقمية فقط دون `+` أو مسافات.
