DROP TABLE IF EXISTS Questions_index;

DROP TRIGGER IF EXISTS after_Questions_insert;
DROP TRIGGER IF EXISTS after_Questions_update;
DROP TRIGGER IF EXISTS after_Questions_delete;

CREATE VIRTUAL TABLE Questions_index USING fts5 (
  title,
  text,
  open,
  close_date,
);

CREATE TRIGGER after_Questions_insert
 AFTER INSERT ON Questions
 BEGIN INSERT INTO Questions_index (
  rowid,
  title,
  text,
  open,
  close_date
) VALUES (
  new.id,
  new.title,
  new.text,
  new.open,
  new.close_date
);
END;

CREATE TRIGGER after_Questions_update
 UPDATE OF
  open,
  close_date
 ON Questions
 BEGIN UPDATE Questions_index
  SET
   open = new.open,
   close_date = new.close_date
  WHERE rowid = old.id;
END;

CREATE TRIGGER after_Questions_delete
 AFTER DELETE ON Questions
 BEGIN DELETE FROM Questions_index
 WHERE rowid = old.id;
END;