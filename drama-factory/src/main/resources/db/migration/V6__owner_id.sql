ALTER TABLE drama_projects ADD COLUMN owner_id VARCHAR(128);

UPDATE drama_projects SET owner_id = 'local' WHERE owner_id IS NULL;

ALTER TABLE drama_projects ALTER COLUMN owner_id SET NOT NULL;
