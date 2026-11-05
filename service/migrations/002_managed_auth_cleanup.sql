-- VisionFit uses Neon Auth; application passwords must not be stored here.
begin;

alter table app_users drop column if exists password_hash;

commit;
