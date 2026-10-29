"""The merged staff schema the bot works with (CLAUDE-MERGE-SCHEMA.md, section 2).

The only place outside SQL text where table and column names live. Used by
the read-only preflight. The bot never creates or changes any of this.
"""

from __future__ import annotations

# Posts the bot creates carry this Source; it only ever touches its own.
SOURCE_BALE = "bale"

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "Users": (
        "Id", "Username", "PasswordHash", "FirstName", "LastName", "Phone", "NationalId",
        "Province", "City", "Education", "ReferrerName", "BaleChatId", "BaleUsername",
        "IsAdmin", "IsActor", "MustChangePassword", "BaleRequireCode", "IsDeleted", "IsActive",
        "NotifyBale", "NotifyMeetings", "NotifyWeekly", "NotifyDelays", "FailedLogins",
        "CreatedAt",
    ),
    "BaleGroups": (
        "Id", "BaleChatId", "Title", "Description", "OrgUnitId", "IsActive", "CreatedAt",
        "UpdatedAt",
    ),
    "BaleGroupMembers": ("UserId", "BaleGroupId", "IsActive", "CreatedAt"),
    "Hashtags": ("Id", "Name", "IsActive", "Description"),
    "Posts": (
        "Id", "AuthorUserId", "BaleGroupId", "BaleMessageId", "ContentType", "Body", "PostedAt",
        "CreatedAt", "OrgUnitId", "Source", "Title", "UserNote",
    ),
    "PostHashtags": ("PostId", "HashtagId"),
    "PostMedia": (
        "Id", "PostId", "MediaType", "BaleFileId", "FileName", "FileSize", "MimeType",
        "StoragePath", "Duration", "Width", "Height", "CreatedAt",
    ),
    "OrgUnits": ("Id", "LevelNo", "Name", "ParentId", "IsActive"),
}  # fmt: skip

# Ids the bot never supplies itself: the database must number them.
AUTO_INCREMENT: tuple[tuple[str, str], ...] = (
    ("Users", "Id"),
    ("BaleGroups", "Id"),
    ("Posts", "Id"),
    ("PostMedia", "Id"),
)

# (table, columns) that must carry a UNIQUE index.
REQUIRED_UNIQUE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Posts", ("BaleGroupId", "BaleMessageId")),  # UQ_Post_BaleMsg — no double archiving
    ("Users", ("BaleChatId",)),  # UQ_Users_BaleChatId
    ("Users", ("Username",)),
    ("BaleGroups", ("BaleChatId",)),
    ("Hashtags", ("Name",)),
)
UNIQUE_NAMES = {("Posts", ("BaleGroupId", "BaleMessageId")): "UQ_Post_BaleMsg"}

# Pre-merge tables. Their presence only causes a warning (zz_old_* copies are fine).
OLD_TABLES: tuple[str, ...] = (
    "Person", "EhyaGroup", "PersonGroup", "Hashtag", "Post", "PostHashtag",
)  # fmt: skip

BOT_TABLES: tuple[str, ...] = tuple(REQUIRED_COLUMNS)
