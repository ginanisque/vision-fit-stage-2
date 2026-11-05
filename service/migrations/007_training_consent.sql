begin;

-- Track whether the customer opted into model training, separate from the
-- measurement-processing consent it augments (consent_version 'visionfit-v2').
alter table capture_sessions
  add column training_consent boolean not null default false;

commit;