CREATE TABLE guild_settings (
    guild_id INTEGER PRIMARY KEY NOT NULL,
    initialized BOOLEAN NOT NULL DEFAULT false,
    allow_user_preferences BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE alarm_sounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    name TEXT NOT NULL CHECK(length(name) <= 40),
    guild_id INTEGER,
    audio_file_name TEXT NOT NULL CHECK(length(audio_file_name) <= 250)
);

CREATE TABLE routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    name TEXT NOT NULL CHECK(length(name) <= 40),
    description TEXT NOT NULL CHECK(length(description) <= 128),
    guild_id INTEGER NOT NULL,
    user_id INTEGER,
    alarm_sound_id INTEGER NOT NULL,
    phases TEXT NOT NULL DEFAULT '[]'
);

INSERT INTO alarm_sounds (name, audio_file_name)
VALUES ("標準（電子音「ピピピピ」）", "alarm_standard.wav");
