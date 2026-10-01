# CyberShield OS

منصة أمن سيبراني متعددة المؤسسات لمتابعة الأصول التي أُضيفت وفُوّضت صراحةً فقط. هذه نسخة MVP عملية، وليست اعتماداً أو شهادة أمنية ولا يُدّعى أنها جاهزة إنتاجياً قبل استكمال متطلبات النشر والاختبار المذكورة أدناه.

## موقع المشروع

المشروع مستقل داخل `cybershield-os/` في مستودع متجر Hekayet Hala. لم تُستبدل ملفات المتجر أو تطبيقه. البنية الخلفية والواجهة والنشر داخل مجلد CyberShield فقط.

## البنية

- `apps/web`: React + TypeScript + Vite + Recharts، واجهة عربية افتراضية مع RTL وتبديل الإنجليزية/LTR. اختير Vite وCSS مخصص بدلاً من Next/Tailwind/shadcn للحفاظ على انسجام هذا المشروع الفرعي مع تطبيق React/Vite في المستودع الأم.
- `apps/api/app`: FastAPI + Pydantic + SQLAlchemy 2، OpenAPI في `/docs`، مصادقة وتفويض وخدمات.
- `apps/api/alembic`: ترحيلات قاعدة البيانات.
- `services/worker`: مهام Celery لفحوص الأصول.
- `infrastructure/nginx`: مدخل موحد للواجهة والـ API.
- `tests`: اختبارات مصادقة وعزل وصلاحيات وفحص ومخاطر وحوادث وتقارير.
- PostgreSQL لتخزين دائم، Redis للمهام، Docker Compose للتشغيل الموحّد.

## تشغيل التطوير المحلي

المتطلبات: Python 3.12، Node 22، Redis، وPostgreSQL (أو SQLite للتطوير والاختبارات). من مجلد `cybershield-os`:

```bash
cp .env.example .env
# حرر .env واجعل القيم المحلية التالية:
# DATABASE_URL=sqlite:///./cybershield-dev.db
# REDIS_URL=redis://localhost:6379/0
# APP_URL=http://localhost:5173
# ENVIRONMENT=development
# COOKIE_SECURE=false
# JWT_SECRET=سر_عشوائي_طويل_خاص_بالتطوير
python3 -m venv .venv
. .venv/bin/activate
pip install -r apps/api/requirements.txt
cd apps/web && npm install && cd ../..
```

شغّل API من جذر المشروع:

```bash
cd apps/api
PYTHONPATH=.:../.. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

في نافذتين إضافيتين من مجلد المشروع: شغّل العامل `PYTHONPATH=apps/api:. celery -A services.worker.celery_app.celery_app worker --loglevel=INFO`، وشغّل الواجهة `cd apps/web && npm run dev`. افتح `http://localhost:5173`؛ يمرّر Vite `/api` إلى الخادم على المنفذ 8000. لإنشاء الفحوص يجب أن يكون Redis والعامل متاحين.

وثائق API: `http://localhost:8000/docs` في التشغيل المحلي و`http://localhost:8080/docs` عند استخدام Compose.

لإنشاء بيانات توضيحية اختياريّة (تُوسم كلها DEVELOPMENT DATA، وجميع الأصول غير مفوضة للفحص):

```bash
PYTHONPATH=apps/api:. SEED_PASSWORD='كلمة-مرور-تطوير-طويلة' .venv/bin/python apps/api/seed.py
```

يدخل مستخدمو التطوير التجريبيون عبر `dev-owner@example.com` و`dev-analyst@example.com` و`dev-viewer@example.com` باستخدام كلمة المرور التي حدّدتها لـ`SEED_PASSWORD`.

## Docker Compose

ثبّت Docker Engine وملحق Compose، ثم:

```bash
cp .env.example .env
# بدّل POSTGRES_PASSWORD وREDIS_PASSWORD إلى قيم عشوائية hex، وJWT_SECRET إلى سر فريد طويل.
# للتشغيل المحلي: APP_URL=http://localhost:8080 وCOOKIE_SECURE=false وENVIRONMENT=development.
docker compose up --build
```

افتح `http://localhost:8080` (وتوثيق API على `/docs`). تحفظ PostgreSQL وRedis بياناتهما في volumes. لإيقاف الخدمات مع إبقاء البيانات: `docker compose down`. حذف volumes يمسح بيانات قاعدة البيانات (لا تستخدم `down -v` إلا بقصد واضح).

## متغيرات البيئة

راجع `.env.example`. أهمها: `DATABASE_URL`, `REDIS_URL`, `REDIS_PASSWORD`, `JWT_SECRET`, `APP_URL`, `ENVIRONMENT`, `COOKIE_SECURE`, وبيانات AI الاختيارية `AI_API_KEY`, `AI_API_BASE`, `AI_MODEL`. مفاتيح SMTP موجودة كبنية مستقبلية، لكن إرسال البريد غير مفعّل حالياً. لا تحفظ `.env` في Git ولا تضع مفاتيح الواجهة.

- في بيئة إنتاج، ولّد قيمة سرية لـ `JWT_SECRET` لا تقل عن 32 حرفاً (مثلاً `openssl rand -hex 32`). يرفض التطبيق سراً قصيراً أو القيمة التطويرية الافتراضية.
- خلف HTTPS فقط: اضبط `APP_URL` على عنوان HTTPS النهائي، و`ENVIRONMENT=production` و`COOKIE_SECURE=true`، واضبط TLS في وكيل/Nginx خارجي موثوق.
- عنوان `REDIS_URL` ينبغي أن يستخدم كلمة المرور المهيأة للخدمة. استخدم قيمة hex لتجنب مشاكل ترميز المحارف الخاصة.

## الترحيلات والاختبارات

```bash
cd apps/api
PYTHONPATH=.:../.. alembic upgrade head
PYTHONPATH=.:../.. alembic current
cd ../..
.venv/bin/pytest
```

في بيئة التطوير تنشئ الخدمة الجداول المفقودة تلقائياً لتسهيل التجربة؛ لا يغني ذلك عن تشغيل Alembic في الإنتاج. API يستخدم SQLite ضمن الاختبارات، لا تتطلب الاختبارات Docker أو اتصالاً بالشبكة.

## نموذج الأمان

- Argon2id لكلمات المرور؛ جلسة JWT قصيرة العمر في Cookie من نوع HttpOnly، مع سجل جلسة قابل للإبطال وCookie مزدوجة لرمز CSRF.
- كل مورد مؤسسي مرتبط بـ `organization_id`، والاستعلامات في الـ API تقيده بسياق عضوية الجلسة. الأدوار تُفرض بالخادم.
- إضافة الأصل تُنشئه `PENDING`. لا يُقبل الفحص إلا بعد تأكيد إداري صريح وبيان مكتوب للتفويض؛ يمكن إبطال التفويض.
- الفحص آمن ومحدود بـ DNS/TLS وطلب HTTPS `HEAD` واحد، مع التحقق من عناوين DNS العامة وتثبيت الاتصال على عنوان IP مُتحقق منه ومنع التحويلات. لا يوجد استغلال أو فحص منافذ أو مسح عشوائي للإنترنت.
- راجع `SECURITY.md` قبل الاستخدام؛ التفويض المكتوب داخل المنتج إقرار من المستخدم ولا يثبت الملكية قانونياً.

## النشر الإنتاجي

استخدم Docker Compose كنقطة بداية لا كخطة توافر عالية. استضف الحاويات خلف TLS وWAF/Proxy موثوق؛ استخدم أسراراً مُدارة وقاعدة PostgreSQL وRedis خارجية ذات نسخ احتياطي ومراقبة؛ قيّد صلاحيات الشبكة الصادرة لعامل الفحص؛ اضبط DNS/حماية SSRF على مستوى الشبكة؛ أضف تخزين تقارير دائماً ونسخاً احتياطية واختبارات استعادة ومراقبة وتدوير أسرار؛ ونفّذ اختبارات أمنية مستقلة. لا تستخدم إعداد HTTP و`COOKIE_SECURE=false` على الإنترنت.

## وظائف متوفرة الآن

التسجيل وإنشاء مؤسسة، الدخول والخروج والجلسات، أدوار أساسية، دعوات يدوية برابط أحادي الاستخدام، لوحة محسوبة، أصول وتفويض، فحوص DNS/TLS/HTTP headers بخلفية Celery، نتائج قابلة لتغيير الحالة، مخاطر، حوادث وملاحظات، أحداث وسجل تدقيق، بحث، تقارير PDF مشتقة من السجلات، ومحادثة AI اختيارية بنطاق المؤسسة عند إعداد مزودها.

## حدود معروفة

هذه ليست كاملة المواصفات المؤسسية بعد: لا تحقق بريد/استعادة كلمة مرور أو MFA؛ لا إدارة اشتراكات/فوترة ولا لوحة SUPER_ADMIN؛ لا NIST/ISO/SOC 2 controls أو حملات تدريب/تصيد؛ لا إشعارات بريد ولا تفضيلاتها أو جداول فحص دورية؛ لا صفحات متخصصة لكل أصل/فحص/حادث ولا عرض فروق إعادة الفحص؛ فحص TLS/الرؤوس لا يقيس كل عوامل درجة الأمان. تحديد المعدل للمصادقة في الذاكرة لكل عملية فقط وليس موزعاً عبر عدة نسخ. الاختبارات الحالية API عبر Pytest (لا توجد اختبارات Playwright/وحدات واجهة بعد). PDF يولّد نصاً إنجليزياً (دعم الخط العربي يحتاج تضمين خط واختبار تشكيل). لا يوجد TLS نهائي في Compose وحده. لم تُجرَ مراجعة اختراق ولا تحقق تشغيل Docker في بيئة العمل الحالية.

يجب التعامل مع النتيجة كنسخة تطوير MVP قابلة للاستكمال لا كخدمة إنتاجية معتمدة.
