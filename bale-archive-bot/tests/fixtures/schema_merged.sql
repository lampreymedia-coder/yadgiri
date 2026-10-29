-- The merged schema of CLAUDE-MERGE-SCHEMA.md section 2, for a THROW-AWAY test
-- database only. The NOT NULL columns of Users / Posts / BaleGroups have NO
-- default on purpose: the tests prove the bot fills every one of them itself.
-- The bot never runs any of this.

CREATE TABLE OrgUnits (
    Id INT NOT NULL AUTO_INCREMENT,
    LevelNo INT NOT NULL,
    Name VARCHAR(200) NOT NULL,
    ParentId INT NULL,
    IsActive TINYINT(1) NOT NULL,
    PRIMARY KEY (Id),
    CONSTRAINT FK_OrgUnits_Parent FOREIGN KEY (ParentId) REFERENCES OrgUnits (Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE Users (
    Id INT NOT NULL AUTO_INCREMENT,
    Username VARCHAR(100) NOT NULL,
    PasswordHash VARCHAR(255) NOT NULL,
    FirstName VARCHAR(100) NOT NULL,
    LastName VARCHAR(100) NOT NULL,
    Phone VARCHAR(20) NULL,
    NationalId VARCHAR(10) NULL,
    Province VARCHAR(50) NULL,
    City VARCHAR(50) NULL,
    Education VARCHAR(50) NULL,
    ReferrerName VARCHAR(100) NULL,
    BaleChatId BIGINT NULL,
    BaleUsername VARCHAR(100) NULL,
    IsAdmin TINYINT(1) NOT NULL,
    IsActor TINYINT(1) NOT NULL,
    MustChangePassword TINYINT(1) NOT NULL,
    BaleRequireCode TINYINT(1) NOT NULL,
    IsDeleted TINYINT(1) NOT NULL,
    IsActive TINYINT(1) NOT NULL,
    NotifyBale TINYINT(1) NOT NULL,
    NotifyMeetings TINYINT(1) NOT NULL,
    NotifyWeekly TINYINT(1) NOT NULL,
    NotifyDelays TINYINT(1) NOT NULL,
    FailedLogins INT NOT NULL,
    CreatedAt DATETIME NOT NULL,
    PRIMARY KEY (Id),
    UNIQUE KEY UQ_Users_Username (Username),
    UNIQUE KEY UQ_Users_BaleChatId (BaleChatId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE BaleGroups (
    Id INT NOT NULL AUTO_INCREMENT,
    BaleChatId BIGINT NOT NULL,
    Title VARCHAR(200) NOT NULL,
    Description VARCHAR(500) NULL,
    OrgUnitId INT NOT NULL,
    IsActive TINYINT(1) NOT NULL,
    CreatedAt DATETIME NOT NULL,
    UpdatedAt DATETIME NULL,
    PRIMARY KEY (Id),
    UNIQUE KEY UQ_BaleGroups_BaleChatId (BaleChatId),
    CONSTRAINT FK_BaleGroups_OrgUnits FOREIGN KEY (OrgUnitId) REFERENCES OrgUnits (Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE BaleGroupMembers (
    UserId INT NOT NULL,
    BaleGroupId INT NOT NULL,
    IsActive TINYINT(1) NOT NULL,
    CreatedAt DATETIME NOT NULL,
    PRIMARY KEY (UserId, BaleGroupId),
    CONSTRAINT FK_BaleGroupMembers_Users FOREIGN KEY (UserId) REFERENCES Users (Id),
    CONSTRAINT FK_BaleGroupMembers_BaleGroups FOREIGN KEY (BaleGroupId) REFERENCES BaleGroups (Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE Hashtags (
    Id INT NOT NULL AUTO_INCREMENT,
    Name VARCHAR(100) NOT NULL,
    IsActive TINYINT(1) NOT NULL,
    Description VARCHAR(500) NULL,
    PRIMARY KEY (Id),
    UNIQUE KEY UQ_Hashtags_Name (Name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE Posts (
    Id BIGINT NOT NULL AUTO_INCREMENT,
    AuthorUserId INT NOT NULL,
    BaleGroupId INT NULL,
    BaleMessageId BIGINT NULL,
    ContentType TINYINT NOT NULL,
    Body LONGTEXT NOT NULL,
    PostedAt DATETIME NOT NULL,
    CreatedAt DATETIME NOT NULL,
    OrgUnitId INT NOT NULL,
    Source VARCHAR(20) NOT NULL,
    Title VARCHAR(300) NULL,
    UserNote TEXT NULL,
    PRIMARY KEY (Id),
    UNIQUE KEY UQ_Post_BaleMsg (BaleGroupId, BaleMessageId),
    CONSTRAINT FK_Posts_Users FOREIGN KEY (AuthorUserId) REFERENCES Users (Id),
    CONSTRAINT FK_Posts_BaleGroups FOREIGN KEY (BaleGroupId) REFERENCES BaleGroups (Id),
    CONSTRAINT FK_Posts_OrgUnits FOREIGN KEY (OrgUnitId) REFERENCES OrgUnits (Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE PostHashtags (
    PostId BIGINT NOT NULL,
    HashtagId INT NOT NULL,
    PRIMARY KEY (PostId, HashtagId),
    CONSTRAINT FK_PostHashtags_Posts FOREIGN KEY (PostId) REFERENCES Posts (Id),
    CONSTRAINT FK_PostHashtags_Hashtags FOREIGN KEY (HashtagId) REFERENCES Hashtags (Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE PostMedia (
    Id BIGINT NOT NULL AUTO_INCREMENT,
    PostId BIGINT NOT NULL,
    MediaType TINYINT NOT NULL,
    BaleFileId VARCHAR(500) NULL,
    FileName VARCHAR(255) NULL,
    FileSize BIGINT NULL,
    MimeType VARCHAR(100) NULL,
    StoragePath VARCHAR(1000) NOT NULL,
    Duration INT NULL,
    Width INT NULL,
    Height INT NULL,
    CreatedAt DATETIME NOT NULL,
    PRIMARY KEY (Id),
    CONSTRAINT FK_PostMedia_Posts FOREIGN KEY (PostId) REFERENCES Posts (Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Left over after the staff migration; the bot must never read these.
CREATE TABLE zz_old_Person (id INT NOT NULL, PRIMARY KEY (id)) ENGINE=InnoDB;
CREATE TABLE DatabankItems (Id INT NOT NULL, PRIMARY KEY (Id)) ENGINE=InnoDB;
