# ArabVoice implementation roadmap

## Phase 1 — foundation
- [x] Create isolated branch `arabvoice-start`
- [x] Add responsive multilingual prototype
- [ ] Move to a dedicated `arabvoice` repository
- [ ] Configure static hosting and custom domain if desired

## Phase 2 — accounts and community
- [ ] Auth provider and database schema
- [ ] User profiles, private/public rooms, moderation roles
- [ ] Real-time text chat, blocking and reporting

## Phase 3 — live audio
- [ ] Select audio provider based on pricing, regions, and expected concurrency
- [ ] Speaker/listener permissions, room moderation, reconnect handling
- [ ] Abuse prevention and operational monitoring

## Phase 4 — virtual economy
- [ ] Server-side coin ledger and gift events
- [ ] Subscription entitlements
- [ ] Payout workflow with provider onboarding, identity verification where required, fraud review, and tax/compliance checks
- [ ] Admin dashboard with audit logs and least-privilege roles

## Release gates
- No real payments before backend verification and provider approval.
- No production secrets in frontend code.
- Test authentication, authorization, rate limits, data deletion, and mobile usability before launch.
