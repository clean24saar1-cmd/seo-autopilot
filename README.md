# SEO Autopilot
Arabic SEO audit MVP.
## Deploy on Render
Build: pip install -r requirements.txt
Start: python backend/server.py
The app listens on Render's PORT environment variable.

## الاشتراكات والدفع

أضيفت حسابات المستخدمين وحدود الاستخدام:
- Free: 2 تحليل كل 30 يومًا، وبحد أقصى 5 صفحات للتحليل.
- Starter: 30 تحليلًا، 25 صفحة لكل تحليل.
- Pro: 150 تحليلًا، 100 صفحة لكل تحليل.
- Agency: 500 تحليل، 250 صفحة لكل تحليل.

### ربط Stripe على Render

أضف Environment Variables إلى خدمة Render:
- `SESSION_SECRET`: سلسلة عشوائية طويلة.
- `STRIPE_SECRET_KEY`: مفتاح Stripe السري.
- `STRIPE_PRICE_STARTER`: Price ID لاشتراك Starter.
- `STRIPE_PRICE_PRO`: Price ID لاشتراك Pro.
- `STRIPE_PRICE_AGENCY`: Price ID لاشتراك Agency.
- `STRIPE_WEBHOOK_SECRET`: Signing secret للـ webhook.
- `APP_URL`: رابط الموقع العام، مثل `https://seo-autopilot-5vcv.onrender.com`.

أنشئ في Stripe Webhook إلى:
`https://seo-autopilot-5vcv.onrender.com/api/stripe/webhook`

ويجب إرسال أحداث الاشتراك الأساسية مثل:
- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`

بدون مفاتيح Stripe لن يتم تحصيل أي مبلغ؛ سيظهر للمستخدم أن الدفع يحتاج إلى إعداد Stripe.
