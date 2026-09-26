-- Appendix A of CLAUDE-BOT-FIX.md (staff schema, MySQL 8.0), copied verbatim.
-- Used ONLY by the test suite to build a throw-away database inside the test
-- machine. The bot itself never runs any of this.

-- =========================================================
-- Bale_Archive - MySQL 8.0
-- =========================================================



-- =========================================================
-- 1. Person
-- =========================================================

CREATE TABLE Person (
    id INT NOT NULL,
    firstname VARCHAR(50) NULL,
    lastname VARCHAR(50) NULL,
    mobile CHAR(11) NULL,
    referrer VARCHAR(50) NULL,
    state VARCHAR(50) NULL,
    city VARCHAR(50) NULL,
    education VARCHAR(50) NULL,
    nasional_code CHAR(10) NULL,
    bale_user_id BIGINT NULL,
    bale_username VARCHAR(100) NULL,
    created_at DATETIME NULL,
    is_active BOOLEAN NULL,

    PRIMARY KEY (id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 2. EhyaGroup
-- =========================================================

CREATE TABLE EhyaGroup (
    id BIGINT NOT NULL AUTO_INCREMENT,
    bale_group_id BIGINT NOT NULL,
    bale_group_name VARCHAR(200) NOT NULL,
    description VARCHAR(500) NULL,
    level TINYINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NULL,

    PRIMARY KEY (id),

    UNIQUE KEY UQ_EhyaGroup_bale_group_id (bale_group_id),

    CONSTRAINT CK_EhyaGroup_level
        CHECK (level >= 1 AND level <= 7)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 3. Hashtag
-- =========================================================

CREATE TABLE Hashtag (
    id TINYINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    PRIMARY KEY (id),

    UNIQUE KEY UQ_Hashtag_name (name)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 4. PersonGroup
-- =========================================================

CREATE TABLE PersonGroup (
    id BIGINT NOT NULL AUTO_INCREMENT,
    person_id INT NOT NULL,
    ehya_group_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    PRIMARY KEY (id),

    UNIQUE KEY UQ_PersonGroup_person_ehyagroup
        (person_id, ehya_group_id),

    KEY IX_PersonGroup_ehyagroup_id
        (ehya_group_id),

    CONSTRAINT FK_PersonGroup_EhyaGroup
        FOREIGN KEY (ehya_group_id)
        REFERENCES EhyaGroup (id),

    CONSTRAINT FK_PersonGroup_Person
        FOREIGN KEY (person_id)
        REFERENCES Person (id)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 5. Post
-- =========================================================

CREATE TABLE Post (
    id BIGINT NOT NULL AUTO_INCREMENT,
    person_id INT NOT NULL,
    ehya_group_id BIGINT NOT NULL,
    bale_message_id BIGINT NOT NULL,
    content_type TINYINT NOT NULL,
    content_text LONGTEXT NOT NULL,
    posted_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY UQ_Post_group_message
        (ehya_group_id, bale_message_id),

    KEY IX_Post_ehyagroup_id
        (ehya_group_id),

    KEY IX_Post_person_id
        (person_id),

    KEY IX_Post_posted_at
        (posted_at),

    CONSTRAINT CK_Post_content_type
        CHECK (content_type >= 1 AND content_type <= 4),

    CONSTRAINT FK_Post_EhyaGroup
        FOREIGN KEY (ehya_group_id)
        REFERENCES EhyaGroup (id),

    CONSTRAINT FK_Post_Person
        FOREIGN KEY (person_id)
        REFERENCES Person (id)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 6. PostHashtag
-- =========================================================

CREATE TABLE PostHashtag (
    post_id BIGINT NOT NULL,
    hashtag_id TINYINT NOT NULL,

    PRIMARY KEY (post_id, hashtag_id),

    KEY IX_PostHashtag_hashtag_id
        (hashtag_id),

    CONSTRAINT FK_PostHashtag_Post
        FOREIGN KEY (post_id)
        REFERENCES Post (id),

    CONSTRAINT FK_PostHashtag_Hashtag
        FOREIGN KEY (hashtag_id)
        REFERENCES Hashtag (id)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 7. PostMedia
-- =========================================================

CREATE TABLE PostMedia (
    id BIGINT NOT NULL AUTO_INCREMENT,
    post_id BIGINT NOT NULL,
    media_type TINYINT NOT NULL,
    bale_file_id VARCHAR(500) NULL,
    file_name VARCHAR(255) NULL,
    file_size BIGINT NULL,
    mime_type VARCHAR(100) NULL,
    storage_path VARCHAR(1000) NOT NULL,
    duration INT NULL,
    width INT NULL,
    height INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY IX_PostMedia_post_id
        (post_id),

    CONSTRAINT CK_PostMedia_media_type
        CHECK (media_type >= 1 AND media_type <= 3),

    CONSTRAINT FK_PostMedia_Post
        FOREIGN KEY (post_id)
        REFERENCES Post (id)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 8. Project
-- =========================================================

CREATE TABLE Project (
    IDProject INT NOT NULL,
    OnvanenProject VARCHAR(50) NULL,
    Sharh LONGTEXT NULL,
    masoleProject INT NULL,
    tedadfaz INT NULL,

    PRIMARY KEY (IDProject)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 9. Naghsh
-- =========================================================

CREATE TABLE Naghsh (
    IDNaghsh INT NOT NULL,
    SharhNaghsh VARCHAR(50) NULL,

    PRIMARY KEY (IDNaghsh)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 10. TarifJalase
-- =========================================================

CREATE TABLE TarifJalase (
    IDJalase INT NOT NULL AUTO_INCREMENT,
    Datekey INT NULL,
    TimeKey INT NULL,
    makan VARCHAR(50) NULL,
    NoeJalase VARCHAR(50) NULL,
    PishDastor CHAR(10) NULL,
    VaziatJalase VARCHAR(50) NULL,
    DabireJalase INT NULL,

    PRIMARY KEY (IDJalase)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 11. Fazz
-- =========================================================

CREATE TABLE Fazz (
    IDfazz INT NOT NULL,
    IDProject INT NULL,
    VaznFazz INT NULL,
    FazChandom INT NULL,
    OnvanFazz VARCHAR(50) NULL,
    TozihFazz LONGTEXT NULL,
    Masool INT NULL,
    Hamzamani BOOLEAN NULL,

    PRIMARY KEY (IDfazz),

    CONSTRAINT FK_Fazz_Project
        FOREIGN KEY (IDProject)
        REFERENCES Project (IDProject)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 12. Gam_Fazz
-- =========================================================

CREATE TABLE Gam_Fazz (
    IDFazz INT NULL,
    gameChandom INT NULL,
    SharheGham VARCHAR(50) NULL,
    Masol INT NULL,
    Mohlat DATE NULL,

    CONSTRAINT FK_Gam_Fazz_Fazz
        FOREIGN KEY (IDFazz)
        REFERENCES Fazz (IDfazz)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 13. Jalase_Person
-- =========================================================

CREATE TABLE Jalase_Person (
    IDJalase INT NULL,
    IDNaghshPerson INT NOT NULL,

    PRIMARY KEY (IDNaghshPerson),

    CONSTRAINT FK_Jalase_Person_TarifJalase
        FOREIGN KEY (IDJalase)
        REFERENCES TarifJalase (IDJalase)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 14. Person_Nagsh
-- =========================================================

CREATE TABLE Person_Nagsh (
    IDperson INT NULL,
    IDNaghsh INT NULL,
    ID_NaghshPerson INT NOT NULL,

    PRIMARY KEY (ID_NaghshPerson),

    CONSTRAINT FK_Person_Nagsh_Jalase_Person
        FOREIGN KEY (ID_NaghshPerson)
        REFERENCES Jalase_Person (IDNaghshPerson),

    CONSTRAINT FK_Person_Nagsh_Naghsh
        FOREIGN KEY (IDNaghsh)
        REFERENCES Naghsh (IDNaghsh),

    CONSTRAINT FK_Person_Nagsh_Person
        FOREIGN KEY (IDperson)
        REFERENCES Person (id)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 15. Peygirijalase
-- =========================================================

CREATE TABLE Peygirijalase (
    IDJalase INT NULL,
    BargozarShod BOOLEAN NULL,
    RavandJalase VARCHAR(50) NULL,
    Mosavabat VARCHAR(50) NULL,
    MauolAnjamMosavabat INT NULL,

    CONSTRAINT FK_Peygirijalase_TarifJalase
        FOREIGN KEY (IDJalase)
        REFERENCES TarifJalase (IDJalase)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 16. Project_Person
-- =========================================================

CREATE TABLE Project_Person (
    IDProject INT NULL,
    IDnaghshperson INT NULL,

    CONSTRAINT FK_Project_Person_Person_Nagsh
        FOREIGN KEY (IDnaghshperson)
        REFERENCES Person_Nagsh (ID_NaghshPerson),

    CONSTRAINT FK_Project_Person_Project
        FOREIGN KEY (IDProject)
        REFERENCES Project (IDProject)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 17. LogTime
-- =========================================================

CREATE TABLE LogTime (
    DAte CHAR(10) NULL,
    Day CHAR(10) NULL,
    Time CHAR(10) NULL,
    idNaghshPerson INT NULL,

    CONSTRAINT FK_LogTime_Person_Nagsh
        FOREIGN KEY (idNaghshPerson)
        REFERENCES Person_Nagsh (ID_NaghshPerson)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
