# ArabVoice — initial prototype

This folder starts the ArabVoice project independently from the SEO app's default branch.

## Current status
- Responsive multilingual landing page (Arabic, German, English; initial language follows browser preference)
- Demo room cards with category filters
- Login/register modal UI
- Clear notice that authentication, real-time audio, payments, gifts, and withdrawals are not yet connected

## Run locally
Open `index.html` in a browser. No build step is required for this prototype.

## Next implementation milestones
1. Create a separate repository named `arabvoice` (recommended) and move this folder's contents to its root.
2. Connect a backend and database; implement secure authentication, profiles, room permissions, moderation, and chat.
3. Integrate real-time audio using an appropriate WebRTC provider.
4. Implement virtual currency and gifts with server-side ledgers and fraud controls.
5. Add subscriptions and payouts only after payment-provider approval, identity checks where required, and legal/compliance review.
6. Add owner/admin roles using server-side authorization. Never trust client-side role flags.
7. Test mobile, accessibility, abuse reporting, data deletion, and security before public launch.

## Important
This is a front-end prototype, not a production-ready chat service. It does not collect credentials or process money.
