begin;

alter table capture_sessions
  add column external_vision_consent boolean not null default false;

commit;
