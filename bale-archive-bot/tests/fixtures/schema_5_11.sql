-- Section 5-11 of CLAUDE-BOT-FIX.md: changes the owner runs as MySQL root.
-- Test suite only.
ALTER TABLE Post DROP CHECK CK_Post_content_type;
ALTER TABLE Post ADD CONSTRAINT CK_Post_content_type CHECK (content_type BETWEEN 1 AND 5);
ALTER TABLE PostMedia DROP CHECK CK_PostMedia_media_type;
ALTER TABLE PostMedia ADD CONSTRAINT CK_PostMedia_media_type CHECK (media_type BETWEEN 1 AND 4);
SET FOREIGN_KEY_CHECKS=0;
ALTER TABLE Person MODIFY id INT NOT NULL AUTO_INCREMENT;
SET FOREIGN_KEY_CHECKS=1;
