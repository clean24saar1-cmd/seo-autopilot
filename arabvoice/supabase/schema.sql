-- ArabVoice initial Supabase schema
-- Run in Supabase SQL Editor only after creating the project.
-- This migration creates the foundation; it does NOT implement voice, payments, or payouts.

create extension if not exists pgcrypto;

create type public.app_role as enum ('user', 'moderator', 'admin');
create type public.room_visibility as enum ('public', 'private');
create type public.wallet_tx_type as enum ('purchase', 'gift_sent', 'gift_received', 'withdrawal', 'refund', 'admin_adjustment');
create type public.withdrawal_status as enum ('pending', 'approved', 'rejected', 'paid');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default 'New user',
  avatar_url text,
  preferred_language text not null default 'en' check (preferred_language in ('ar','de','en')),
  role public.app_role not null default 'user',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.rooms (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles(id) on delete restrict,
  name text not null check (char_length(name) between 2 and 80),
  description text not null default '',
  visibility public.room_visibility not null default 'public',
  is_active boolean not null default true,
  capacity integer not null default 20 check (capacity between 2 and 100),
  created_at timestamptz not null default now()
);

create table public.room_members (
  room_id uuid not null references public.rooms(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  joined_at timestamptz not null default now(),
  is_speaker boolean not null default false,
  primary key (room_id, user_id)
);

create table public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  room_id uuid not null references public.rooms(id) on delete cascade,
  sender_id uuid not null references public.profiles(id) on delete restrict,
  body text not null check (char_length(body) between 1 and 2000),
  created_at timestamptz not null default now()
);

create table public.gifts (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  image_url text,
  coin_price integer not null check (coin_price > 0),
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.wallets (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  coin_balance bigint not null default 0 check (coin_balance >= 0),
  earnings_balance bigint not null default 0 check (earnings_balance >= 0),
  updated_at timestamptz not null default now()
);

create table public.wallet_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete restrict,
  type public.wallet_tx_type not null,
  coin_delta bigint not null default 0,
  earnings_delta bigint not null default 0,
  reference_id uuid,
  note text not null default '',
  created_at timestamptz not null default now()
);

create table public.gift_events (
  id uuid primary key default gen_random_uuid(),
  room_id uuid references public.rooms(id) on delete set null,
  sender_id uuid not null references public.profiles(id) on delete restrict,
  recipient_id uuid not null references public.profiles(id) on delete restrict,
  gift_id uuid not null references public.gifts(id) on delete restrict,
  quantity integer not null default 1 check (quantity between 1 and 100),
  created_at timestamptz not null default now()
);

create table public.withdrawal_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete restrict,
  amount_minor bigint not null check (amount_minor > 0),
  currency text not null default 'EUR' check (currency in ('EUR','USD')),
  payout_method text not null check (payout_method in ('paypal','bank_transfer')),
  payout_details jsonb not null default '{}'::jsonb,
  status public.withdrawal_status not null default 'pending',
  admin_note text not null default '',
  created_at timestamptz not null default now(),
  reviewed_at timestamptz
);

create table public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  plan_code text not null,
  status text not null default 'inactive' check (status in ('inactive','active','past_due','cancelled','expired')),
  provider text,
  provider_reference text,
  current_period_end timestamptz,
  created_at timestamptz not null default now()
);

create table public.app_settings (
  key text primary key,
  value jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index rooms_active_created_idx on public.rooms(is_active, created_at desc);
create index messages_room_created_idx on public.chat_messages(room_id, created_at desc);
create index transactions_user_created_idx on public.wallet_transactions(user_id, created_at desc);
create index withdrawals_status_created_idx on public.withdrawal_requests(status, created_at desc);

-- Create a profile and an empty wallet for each new auth account.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, preferred_language)
  values (
    new.id,
    coalesce(nullif(new.raw_user_meta_data ->> 'display_name', ''), 'New user'),
    case
      when left(coalesce(new.raw_user_meta_data ->> 'preferred_language', ''), 2) in ('ar','de','en')
      then left(new.raw_user_meta_data ->> 'preferred_language', 2)
      else 'en'
    end
  );
  insert into public.wallets (user_id) values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.rooms enable row level security;
alter table public.room_members enable row level security;
alter table public.chat_messages enable row level security;
alter table public.gifts enable row level security;
alter table public.wallets enable row level security;
alter table public.wallet_transactions enable row level security;
alter table public.gift_events enable row level security;
alter table public.withdrawal_requests enable row level security;
alter table public.subscriptions enable row level security;
alter table public.app_settings enable row level security;

-- Users may read public profile fields and edit only their own display fields.
create policy "Profiles are readable by signed-in users" on public.profiles
for select to authenticated using (true);
create policy "Users update their own profile" on public.profiles
for update to authenticated using (auth.uid() = id) with check (auth.uid() = id);

create policy "Signed-in users can view active public rooms" on public.rooms
for select to authenticated using (is_active = true and visibility = 'public');
create policy "Room owners can create rooms" on public.rooms
for insert to authenticated with check (auth.uid() = owner_id);
create policy "Owners can update their rooms" on public.rooms
for update to authenticated using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

create policy "Members can view room membership" on public.room_members
for select to authenticated using (auth.uid() = user_id);
create policy "Users can join as themselves" on public.room_members
for insert to authenticated with check (auth.uid() = user_id);
create policy "Users can leave as themselves" on public.room_members
for delete to authenticated using (auth.uid() = user_id);

create policy "Signed-in users can read messages in public rooms" on public.chat_messages
for select to authenticated using (
  exists (
    select 1 from public.rooms r
    where r.id = room_id and r.is_active = true and r.visibility = 'public'
  )
);
create policy "Users can send messages as themselves to public rooms" on public.chat_messages
for insert to authenticated with check (
  auth.uid() = sender_id and exists (
    select 1 from public.rooms r
    where r.id = room_id and r.is_active = true and r.visibility = 'public'
  )
);

create policy "Signed-in users can view active gifts" on public.gifts
for select to authenticated using (is_active = true);

create policy "Users can view their own wallet" on public.wallets
for select to authenticated using (auth.uid() = user_id);
create policy "Users can view their own transactions" on public.wallet_transactions
for select to authenticated using (auth.uid() = user_id);
create policy "Gift events visible to sender or recipient" on public.gift_events
for select to authenticated using (auth.uid() = sender_id or auth.uid() = recipient_id);
create policy "Users can view their own withdrawal requests" on public.withdrawal_requests
for select to authenticated using (auth.uid() = user_id);
create policy "Users can create withdrawal requests for themselves" on public.withdrawal_requests
for insert to authenticated with check (auth.uid() = user_id and status = 'pending');
create policy "Users can view their own subscriptions" on public.subscriptions
for select to authenticated using (auth.uid() = user_id);

-- Deliberately no client write policies for balances, transactions, gifts, app settings,
-- subscription status, or withdrawal decisions. Those must be handled by trusted server code.
-- Do not store card details or PayPal passwords in payout_details.
