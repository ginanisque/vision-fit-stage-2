-- Allow object-store deletion to be retried without losing storage keys.
alter type processing_status add value if not exists 'deleting';
