-- QAZGAME club database schema (Supabase / Postgres). Run ONCE on a new Supabase project, then run seed.sql from make_club.py.
-- Club-specific data (PCs, tariffs, secrets, admin e-mail) is NOT here: it comes from seed.sql.

create table public.pcs(
  id int primary key,
  zone text not null,
  status text not null default 'available' check (status in ('available','occupied','booked')),
  last_seen timestamptz,
  client text, phone text,
  session_end timestamptz,
  mac text,
  secret text not null default replace(gen_random_uuid()::text,'-',''),
  lock_secret text not null default replace(gen_random_uuid()::text,'-',''),
  unlock_code text,
  unlocked boolean not null default false,
  unlock_fails int not null default 0
);
create table public.tariffs(
  zone text not null, key text not null, label jsonb not null, hours int not null, price int not null,
  primary key(zone,key)
);
create table public.requests(
  id uuid primary key default gen_random_uuid(),
  pc_id int not null references public.pcs(id),
  tariff_label jsonb, hours int not null check (hours between 1 and 12),
  price int not null check (price >= 0), eta int,
  name text not null check (length(name) between 1 and 60),
  phone text not null check (length(phone) between 5 and 20),
  receipt boolean not null default false,
  receipt_path text,
  state text not null default 'new' check (state in ('new','done','rejected')),
  code text,
  token text not null default replace(gen_random_uuid()::text,'-',''),
  created_at timestamptz not null default now()
);
create table public.commands(
  id bigserial primary key,
  pc_id int not null references public.pcs(id),
  action text not null check (action in ('wake','shutdown','restart','lock','unlock')),
  state text not null default 'pending' check (state in ('pending','done','failed')),
  created_at timestamptz not null default now(), done_at timestamptz
);
create table public.sessions(
  id bigserial primary key,
  pc_id int not null references public.pcs(id),
  client text, phone text, tariff_label jsonb,
  minutes int not null, price int not null,
  started_at timestamptz not null default now(), ended_at timestamptz
);
create table public.log(id bigserial primary key, ts timestamptz not null default now(), text text not null);
create table public.settings(key text primary key, value text not null);
create table public.admins(user_id uuid primary key references auth.users(id) on delete cascade);

alter table public.pcs enable row level security;
alter table public.tariffs enable row level security;
alter table public.requests enable row level security;
alter table public.commands enable row level security;
alter table public.sessions enable row level security;
alter table public.log enable row level security;
alter table public.settings enable row level security;
alter table public.admins enable row level security;

create or replace function public.is_admin() returns boolean language sql stable security definer set search_path=public as $$
  select exists(select 1 from public.admins where user_id = auth.uid())
$$;

create policy admin_all on public.pcs for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy admin_all on public.tariffs for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy admin_all on public.requests for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy admin_all on public.commands for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy admin_all on public.sessions for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy admin_all on public.log for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy admin_all on public.settings for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy admin_read_self on public.admins for select to authenticated using (user_id = auth.uid());

revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;

-- ===== public (anonymous) functions =====
create or replace function public.public_pcs() returns table(id int, zone text, status text) language sql security definer set search_path=public as $$
  select p.id, p.zone, p.status from public.pcs p order by p.id
$$;
create or replace function public.public_tariffs() returns table(zone text, key text, label jsonb, hours int, price int) language sql security definer set search_path=public as $$
  select t.zone, t.key, t.label, t.hours, t.price from public.tariffs t
$$;
create or replace function public.create_request(p_pc int, p_tariff text, p_eta int, p_name text, p_phone text)
returns table(id uuid, token text) language plpgsql security definer set search_path=public as $$
declare z text; t public.tariffs%rowtype; r public.requests%rowtype;
begin
  select p.zone into z from public.pcs p where p.id = p_pc and p.status = 'available';
  if z is null then raise exception 'pc_unavailable'; end if;
  select * into t from public.tariffs x where x.zone = z and x.key = p_tariff;
  if not found then raise exception 'bad_tariff'; end if;
  if (select count(*) from public.requests q where q.phone = p_phone and q.state = 'new' and q.created_at > now() - interval '1 hour') >= 3 then
    raise exception 'too_many';
  end if;
  insert into public.requests(pc_id, tariff_label, hours, price, eta, name, phone)
  values (p_pc, t.label, t.hours, t.price, least(greatest(coalesce(p_eta,10),0),60), left(trim(p_name),60), left(trim(p_phone),20))
  returning * into r;
  return query select r.id, r.token;
end $$;
create or replace function public.get_request(p_id uuid, p_token text)
returns table(state text, code text, pc_id int, label jsonb, price int) language sql security definer set search_path=public as $$
  select r.state, r.code, r.pc_id, r.tariff_label, r.price from public.requests r where r.id = p_id and r.token = p_token
$$;
create or replace function public.mark_receipt(p_id uuid, p_token text, p_path text default null) returns void language sql security definer set search_path=public as $$
  update public.requests set receipt = true, receipt_path = coalesce(left(p_path,200), receipt_path) where id = p_id and token = p_token
$$;

-- ===== internal helpers =====
create or replace function public._release_pc(p_pc int, p_shutdown boolean) returns void language plpgsql security definer set search_path=public as $$
begin
  update public.sessions set ended_at = now() where pc_id = p_pc and ended_at is null;
  update public.pcs set status='available', client=null, phone=null, session_end=null, unlock_code=null, unlocked=false, unlock_fails=0 where id = p_pc;
  if p_shutdown then insert into public.commands(pc_id,action) values (p_pc,'shutdown'); end if;
end $$;
-- auto-end sessions 2 min after time is up; release no-shows after 30 min
create or replace function public.expire_sessions() returns void language plpgsql security definer set search_path=public as $$
declare r record;
begin
  for r in select id from public.pcs where status='occupied' and unlocked and session_end is not null and session_end < now() - interval '2 minutes' loop
    perform public._release_pc(r.id, true);
    insert into public.log(text) values ('Auto-ended (time up): PC '||r.id);
  end loop;
  for r in select p.id from public.pcs p where p.status='occupied' and not p.unlocked and exists(
      select 1 from public.sessions s where s.pc_id = p.id and s.ended_at is null and s.started_at < now() - interval '30 minutes') loop
    perform public._release_pc(r.id, false);
    insert into public.log(text) values ('No-show released: PC '||r.id);
  end loop;
end $$;

-- ===== admin functions =====
create or replace function public.confirm_request(p_id uuid) returns text language plpgsql security definer set search_path=public as $$
declare r public.requests%rowtype; c text;
begin
  if not public.is_admin() then raise exception 'forbidden'; end if;
  select * into r from public.requests where id = p_id and state = 'new' for update;
  if not found then raise exception 'not_found'; end if;
  if (select status from public.pcs where id = r.pc_id) <> 'available' then raise exception 'pc_busy'; end if;
  c := lpad((floor(random()*9000)+1000)::int::text, 4, '0');
  update public.pcs set status='occupied', client=r.name, phone=r.phone, session_end=null, unlock_code=c, unlocked=false, unlock_fails=0 where id = r.pc_id;
  insert into public.sessions(pc_id,client,phone,tariff_label,minutes,price) values (r.pc_id,r.name,r.phone,r.tariff_label,r.hours*60,r.price);
  update public.requests set state='done', code=c where id = p_id;
  insert into public.commands(pc_id,action) values (r.pc_id,'wake');
  insert into public.log(text) values ('Confirmed: PC '||r.pc_id||' · '||r.name||' · '||r.price);
  return c;
end $$;
create or replace function public.reject_request(p_id uuid) returns void language plpgsql security definer set search_path=public as $$
begin
  if not public.is_admin() then raise exception 'forbidden'; end if;
  update public.requests set state='rejected' where id = p_id and state='new';
  insert into public.log(text) values ('Rejected request');
end $$;
create or replace function public.start_session(p_pc int, p_client text, p_phone text, p_hours int, p_price int) returns void language plpgsql security definer set search_path=public as $$
begin
  if not public.is_admin() then raise exception 'forbidden'; end if;
  update public.pcs set status='occupied', client=p_client, phone=p_phone, session_end=now()+make_interval(hours=>p_hours),
    unlock_code=lpad((floor(random()*9000)+1000)::int::text,4,'0'), unlocked=true, unlock_fails=0 where id = p_pc;
  insert into public.sessions(pc_id,client,phone,minutes,price) values (p_pc,p_client,p_phone,p_hours*60,p_price);
  insert into public.commands(pc_id,action) values (p_pc,'wake');
  insert into public.log(text) values ('Session started: PC '||p_pc||' · '||coalesce(p_client,'-'));
end $$;
create or replace function public.extend_session(p_pc int, p_minutes int, p_price int) returns void language plpgsql security definer set search_path=public as $$
begin
  if not public.is_admin() then raise exception 'forbidden'; end if;
  update public.pcs set session_end = session_end + make_interval(mins=>p_minutes) where id = p_pc and status='occupied';
  update public.sessions set minutes = minutes + p_minutes, price = price + p_price where id = (select max(s.id) from public.sessions s where s.pc_id = p_pc and s.ended_at is null);
  insert into public.log(text) values ('Extended: PC '||p_pc||' +'||p_minutes||' min');
end $$;
create or replace function public.end_session(p_pc int, p_shutdown boolean default true) returns void language plpgsql security definer set search_path=public as $$
begin
  if not public.is_admin() then raise exception 'forbidden'; end if;
  perform public._release_pc(p_pc, p_shutdown);
  insert into public.log(text) values ('Session ended: PC '||p_pc);
end $$;
create or replace function public.unlock_pc(p_pc int) returns void language plpgsql security definer set search_path=public as $$
declare s public.sessions%rowtype;
begin
  if not public.is_admin() then raise exception 'forbidden'; end if;
  select * into s from public.sessions where pc_id = p_pc and ended_at is null order by id desc limit 1;
  if not found then raise exception 'no_session'; end if;
  update public.pcs set unlocked=true, session_end = coalesce(session_end, now()+make_interval(mins=>s.minutes)) where id = p_pc and status='occupied';
  update public.sessions set started_at = now() where id = s.id;
  insert into public.log(text) values ('Unlocked by operator: PC '||p_pc);
end $$;
create or replace function public.send_command(p_pc int, p_action text) returns void language plpgsql security definer set search_path=public as $$
begin
  if not public.is_admin() then raise exception 'forbidden'; end if;
  insert into public.commands(pc_id,action) values (p_pc,p_action);
  insert into public.log(text) values ('Command '||p_action||': PC '||p_pc);
end $$;

-- ===== PC agent, lock screen, Wake-on-LAN agent =====
create or replace function public.agent_hello(p_pc int, p_secret text, p_mac text) returns void language plpgsql security definer set search_path=public as $$
begin
  if not exists(select 1 from public.pcs p where p.id = p_pc and p.secret = p_secret) then raise exception 'forbidden'; end if;
  update public.pcs set mac = upper(left(regexp_replace(p_mac,'[^0-9A-Fa-f]','','g'),12)), last_seen = now() where id = p_pc;
end $$;
create or replace function public.agent_poll(p_pc int, p_secret text) returns table(cmd_id bigint, action text) language plpgsql security definer set search_path=public as $$
begin
  if not exists(select 1 from public.pcs p where p.id = p_pc and p.secret = p_secret) then raise exception 'forbidden'; end if;
  update public.pcs set last_seen = now() where id = p_pc;
  perform public.expire_sessions();
  update public.commands cm set state = 'failed', done_at = now()
    where cm.pc_id = p_pc and cm.state = 'pending' and cm.action <> 'wake' and cm.created_at < now() - interval '2 minutes';
  return query select c.id, c.action from public.commands c
    where c.pc_id = p_pc and c.state = 'pending' and c.action in ('shutdown','restart','lock','unlock') order by c.id;
end $$;
create or replace function public.agent_ack(p_pc int, p_secret text, p_cmd bigint, p_ok boolean) returns void language plpgsql security definer set search_path=public as $$
begin
  if not exists(select 1 from public.pcs p where p.id = p_pc and p.secret = p_secret) then raise exception 'forbidden'; end if;
  update public.commands set state = case when p_ok then 'done' else 'failed' end, done_at = now() where id = p_cmd and pc_id = p_pc;
end $$;
create or replace function public.agent_status(p_pc int, p_secret text) returns table(status text, client text, session_end timestamptz, unlocked boolean, server_now timestamptz, fails int)
language plpgsql security definer set search_path=public as $$
begin
  if not exists(select 1 from public.pcs p where p.id = p_pc and p.lock_secret = p_secret) then raise exception 'forbidden'; end if;
  return query select p.status, p.client, p.session_end, p.unlocked, now(), p.unlock_fails from public.pcs p where p.id = p_pc;
end $$;
create or replace function public.agent_unlock(p_pc int, p_secret text, p_code text) returns boolean language plpgsql security definer set search_path=public as $$
declare s public.sessions%rowtype; ok boolean;
begin
  if not exists(select 1 from public.pcs p where p.id = p_pc and p.lock_secret = p_secret) then raise exception 'forbidden'; end if;
  select exists(select 1 from public.pcs p where p.id = p_pc and p.status='occupied' and not p.unlocked and p.unlock_fails < 5
                and p.unlock_code is not null and p.unlock_code = p_code) into ok;
  if not ok then
    update public.pcs set unlock_fails = unlock_fails + 1 where id = p_pc and status='occupied' and not unlocked;
    return false;
  end if;
  select * into s from public.sessions where pc_id = p_pc and ended_at is null order by id desc limit 1;
  update public.pcs set unlocked=true, session_end = now() + make_interval(mins=>s.minutes) where id = p_pc;
  update public.sessions set started_at = now() where id = s.id;
  insert into public.log(text) values ('Unlocked by client: PC '||p_pc);
  return true;
end $$;
create or replace function public.wol_poll(p_secret text) returns table(cmd_id bigint, pc_id int, mac text) language plpgsql security definer set search_path=public as $$
begin
  if p_secret is distinct from (select s.value from public.settings s where s.key = 'wol_secret') then raise exception 'forbidden'; end if;
  update public.commands set state='failed', done_at=now() where action='wake' and state='pending' and created_at < now() - interval '2 minutes';
  return query select c.id, c.pc_id, p.mac from public.commands c join public.pcs p on p.id = c.pc_id
    where c.action='wake' and c.state='pending' order by c.id;
end $$;
create or replace function public.wol_ack(p_secret text, p_cmd bigint, p_ok boolean) returns void language plpgsql security definer set search_path=public as $$
begin
  if p_secret is distinct from (select s.value from public.settings s where s.key = 'wol_secret') then raise exception 'forbidden'; end if;
  update public.commands set state = case when p_ok then 'done' else 'failed' end, done_at = now() where id = p_cmd and action='wake';
end $$;

-- ===== receipts (Storage) =====
create or replace function public.can_upload_receipt(p text) returns boolean language sql stable security definer set search_path=public as $$
  select exists(select 1 from public.requests r where r.id::text = split_part(p,'/',1) and split_part(p,'/',2) like r.token || '%' and r.state in ('new','done'))
$$;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('receipts','receipts',false,5242880,array['image/jpeg','image/png','image/webp','image/heic','application/pdf'])
on conflict (id) do nothing;
create policy receipts_upload on storage.objects for insert to anon, authenticated with check (bucket_id = 'receipts' and public.can_upload_receipt(name));
create policy receipts_admin_read on storage.objects for select to authenticated using (bucket_id = 'receipts' and public.is_admin());

-- ===== first admin: the e-mail from settings.admin_email becomes admin when its account is confirmed =====
create or replace function public.grant_first_admin() returns trigger language plpgsql security definer set search_path=public as $$
begin
  if new.email_confirmed_at is not null and lower(new.email) = (select lower(s.value) from public.settings s where s.key = 'admin_email') then
    insert into public.admins(user_id) values (new.id) on conflict do nothing;
  end if;
  return new;
end $$;
create trigger grant_first_admin_trg after insert or update of email_confirmed_at on auth.users
  for each row execute function public.grant_first_admin();

-- ===== grants =====
revoke execute on all functions in schema public from public, anon, authenticated;
grant execute on function public.public_pcs(), public.public_tariffs(), public.create_request(int,text,int,text,text), public.get_request(uuid,text), public.mark_receipt(uuid,text,text),
  public.agent_hello(int,text,text), public.agent_poll(int,text), public.agent_ack(int,text,bigint,boolean), public.agent_status(int,text), public.agent_unlock(int,text,text),
  public.wol_poll(text), public.wol_ack(text,bigint,boolean), public.can_upload_receipt(text) to anon, authenticated;
grant execute on function public.is_admin(), public.confirm_request(uuid), public.reject_request(uuid), public.start_session(int,text,text,int,int),
  public.extend_session(int,int,int), public.end_session(int,boolean), public.unlock_pc(int), public.send_command(int,text) to authenticated;
