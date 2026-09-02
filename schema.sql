-- TRAFFIC HUB schema (PROJECT_SPEC_v3 §4). MariaDB 10.6, utf8mb4.
-- Contains every table for all phases. No prepaid point tables: campaigns are paid per order via PG (v3.1).

CREATE DATABASE IF NOT EXISTS traffic_hub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE traffic_hub;

SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------- users
CREATE TABLE IF NOT EXISTS users (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  kakao_id        VARCHAR(40) UNIQUE,
  email           VARCHAR(120) UNIQUE,
  password_hash   VARCHAR(255) NULL,
  nickname        VARCHAR(30) NOT NULL,
  phone           VARCHAR(20),
  role            ENUM('user','admin') NOT NULL DEFAULT 'user',
  grade           ENUM('biz','agency','master') NOT NULL DEFAULT 'biz',
  biz_name        VARCHAR(60) NULL,
  biz_no          VARCHAR(20) NULL,
  biz_type        VARCHAR(40) NULL,
  biz_item        VARCHAR(40) NULL,
  biz_email       VARCHAR(120) NULL,
  notify_campaign TINYINT(1) NOT NULL DEFAULT 1,
  notify_comment  TINYINT(1) NOT NULL DEFAULT 1,
  notify_event    TINYINT(1) NOT NULL DEFAULT 0,
  is_agency       TINYINT(1) NOT NULL DEFAULT 0,
  status          ENUM('active','suspended') NOT NULL DEFAULT 'active',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- media / campaigns
CREATE TABLE IF NOT EXISTS media (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  channel           ENUM('place','store','coupang') NOT NULL,
  group_name        VARCHAR(40) NOT NULL DEFAULT '',
  name              VARCHAR(40) NOT NULL,
  tagline           VARCHAR(80) NULL,
  logo_url          VARCHAR(255) NULL,
  color             CHAR(7) NOT NULL DEFAULT '#4B5563',
  unit_price        INT NOT NULL,
  list_price        INT NULL,
  min_days          INT NOT NULL DEFAULT 3,
  min_daily         INT NOT NULL DEFAULT 50,
  max_daily         INT NOT NULL DEFAULT 500,
  efficiency_auto   TINYINT NOT NULL DEFAULT 0,
  efficiency_manual TINYINT NULL,
  cutoff_time       TIME NOT NULL DEFAULT '13:30:00',
  same_day          TINYINT(1) NOT NULL DEFAULT 1,
  description       TEXT NULL,
  badge             ENUM('rec','best','new') NULL,
  eff_level         ENUM('normal','good','best') NOT NULL DEFAULT 'good',
  eff_note          VARCHAR(120) NULL,
  sort              INT NOT NULL DEFAULT 0,
  is_active         TINYINT(1) NOT NULL DEFAULT 1,
  INDEX idx_media_channel (channel, is_active, sort)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS campaigns (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  order_no         CHAR(10) NOT NULL UNIQUE,
  user_id          INT NOT NULL,
  channel          ENUM('place','store','coupang') NOT NULL,
  media_id         INT NOT NULL,
  status           ENUM('pay_wait','review','approved','running','rejected','done','stopped','cancelled') NOT NULL DEFAULT 'pay_wait',
  biz_name         VARCHAR(80) NOT NULL,
  product_name     VARCHAR(120) NULL,
  target_url       VARCHAR(500) NOT NULL,
  main_keyword     VARCHAR(60) NOT NULL,
  sub_keywords     JSON NULL,
  setting_keywords JSON NULL,
  keyword_mode     ENUM('ai','manual') NOT NULL DEFAULT 'ai',
  extra            JSON NULL,
  start_date       DATE NOT NULL,
  end_date         DATE NOT NULL,
  daily_qty        INT NOT NULL,
  total_qty        INT NOT NULL,
  unit_price       INT NOT NULL,
  discount         INT NOT NULL DEFAULT 0,
  vat              INT NOT NULL DEFAULT 0,
  paid_amount      INT NOT NULL,
  pay_method       ENUM('card','bank') NOT NULL DEFAULT 'card',
  paid_at          DATETIME NULL,
  refund_amount    INT NOT NULL DEFAULT 0,
  warn_words       VARCHAR(300) NULL,
  rank_start       INT NULL,
  rank_now         INT NULL,
  reject_reason    VARCHAR(300) NULL,
  admin_memo       TEXT NULL,
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_campaign_user (user_id, channel, status),
  INDEX idx_campaign_status (status, created_at),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (media_id) REFERENCES media(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS payments (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  campaign_id   INT NOT NULL,
  user_id       INT NOT NULL,
  method        ENUM('card','bank') NOT NULL,
  amount        INT NOT NULL,
  status        ENUM('pending','paid','partial_refund','refunded','cancelled','expired') NOT NULL DEFAULT 'pending',
  pg_provider   VARCHAR(20) NULL,
  pg_tid        VARCHAR(64) NULL,
  depositor     VARCHAR(40) NULL,
  name_mismatch TINYINT(1) NOT NULL DEFAULT 0,
  bank_due_at   DATETIME NULL,
  paid_at       DATETIME NULL,
  refund_amount INT NOT NULL DEFAULT 0,
  refunded_at   DATETIME NULL,
  memo          VARCHAR(200) NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_payments_campaign (campaign_id),
  INDEX idx_payments_status (status, method, bank_due_at),
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS campaign_daily (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  campaign_id INT NOT NULL,
  date        DATE NOT NULL,
  done_qty    INT NOT NULL DEFAULT 0,
  rank        INT NULL,
  UNIQUE KEY uq_campaign_daily (campaign_id, date),
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS status_log (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  campaign_id INT NOT NULL,
  from_status VARCHAR(12) NULL,
  to_status   VARCHAR(12) NOT NULL,
  actor_id    INT NULL,
  memo        VARCHAR(300) NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_status_log_campaign (campaign_id, created_at),
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS forbidden_words (
  id       INT AUTO_INCREMENT PRIMARY KEY,
  word     VARCHAR(60) NOT NULL,
  channel  ENUM('place','store','coupang') NULL,
  severity ENUM('warn','block') NOT NULL DEFAULT 'warn'
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS admin_log (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  admin_id    INT NOT NULL,
  action      VARCHAR(40) NOT NULL,
  target_type VARCHAR(30) NULL,
  target_id   INT NULL,
  summary     VARCHAR(300) NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_admin_log_created (created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS settings (
  k          VARCHAR(40) PRIMARY KEY,
  v          VARCHAR(500) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- contents / notifications
CREATE TABLE IF NOT EXISTS contents (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  board          ENUM('notice','info','series') NOT NULL,
  channel        ENUM('store','place','coupang') NULL,
  category       VARCHAR(20) NULL,
  series_no      INT NULL,
  title          VARCHAR(200) NOT NULL,
  body           MEDIUMTEXT NULL,
  status         ENUM('draft','scheduled','published') NOT NULL DEFAULT 'published',
  publish_at     DATETIME NULL,
  is_pinned      TINYINT(1) NOT NULL DEFAULT 0,
  show_dashboard TINYINT(1) NOT NULL DEFAULT 1,
  notify         TINYINT(1) NOT NULL DEFAULT 0,
  views          INT NOT NULL DEFAULT 0,
  author_id      INT NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_contents_board (board, status, is_pinned, publish_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS series_reads (
  user_id    INT NOT NULL,
  content_id INT NOT NULL,
  PRIMARY KEY (user_id, content_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS notifications (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  user_id    INT NOT NULL,
  type       VARCHAR(30) NOT NULL,
  title      VARCHAR(200) NOT NULL,
  link       VARCHAR(300) NULL,
  is_read    TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_notifications_user (user_id, is_read, created_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- store slots / keyword tools
CREATE TABLE IF NOT EXISTS store_slots (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  user_id     INT NOT NULL,
  keyword     VARCHAR(60) NOT NULL,
  product_url VARCHAR(500) NULL,
  store_name  VARCHAR(80) NULL,
  pc_cnt      INT NOT NULL DEFAULT 0,
  mo_cnt      INT NOT NULL DEFAULT 0,
  reco_qty    INT NOT NULL DEFAULT 1,
  fetched_at  DATETIME NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_store_slots_user (user_id),
  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS slot_daily (
  slot_id    INT NOT NULL,
  date       DATE NOT NULL,
  rank_total INT NULL,
  rank_price INT NULL,
  PRIMARY KEY (slot_id, date),
  FOREIGN KEY (slot_id) REFERENCES store_slots(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS keyword_cache (
  keyword    VARCHAR(60) PRIMARY KEY,
  pc_cnt     INT NOT NULL DEFAULT 0,
  mo_cnt     INT NOT NULL DEFAULT 0,
  comp       VARCHAR(10) NULL,
  fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS related_cache (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  seed       VARCHAR(60) NOT NULL,
  keyword    VARCHAR(60) NOT NULL,
  pc_cnt     INT NOT NULL DEFAULT 0,
  mo_cnt     INT NOT NULL DEFAULT 0,
  fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_related_seed (seed)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS keyword_query_log (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  user_id    INT NULL,
  ip         VARCHAR(45) NOT NULL,
  tool       VARCHAR(20) NOT NULL,
  query      VARCHAR(300) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_kql_user (user_id, created_at),
  INDEX idx_kql_ip (ip, created_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- community
CREATE TABLE IF NOT EXISTS boards (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  slug       VARCHAR(20) NOT NULL UNIQUE,
  name       VARCHAR(30) NOT NULL,
  is_anon    TINYINT(1) NOT NULL DEFAULT 1,
  write_role ENUM('user','admin') NOT NULL DEFAULT 'user'
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS posts (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  board_id            INT NOT NULL,
  user_id             INT NOT NULL,
  anon_nick           VARCHAR(20) NOT NULL,
  channel_tag         ENUM('place','store','coupang','tool') NULL,
  title               VARCHAR(200) NOT NULL,
  body                TEXT NOT NULL,
  image_url           VARCHAR(300) NULL,
  is_solved           TINYINT(1) NOT NULL DEFAULT 0,
  accepted_comment_id INT NULL,
  views               INT NOT NULL DEFAULT 0,
  likes               INT NOT NULL DEFAULT 0,
  report_cnt          INT NOT NULL DEFAULT 0,
  is_blind            TINYINT(1) NOT NULL DEFAULT 0,
  created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_posts_board (board_id, is_blind, created_at),
  INDEX idx_posts_user (user_id),
  FOREIGN KEY (board_id) REFERENCES boards(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS post_nicks (
  post_id INT NOT NULL,
  user_id INT NOT NULL,
  nick    VARCHAR(20) NOT NULL,
  PRIMARY KEY (post_id, user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS media_nicks (
  media_id INT NOT NULL,
  user_id  INT NOT NULL,
  nick     VARCHAR(20) NOT NULL,
  PRIMARY KEY (media_id, user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS media_comments (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  media_id   INT NOT NULL,
  user_id    INT NOT NULL,
  anon_nick  VARCHAR(20) NOT NULL,
  body       VARCHAR(500) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_media_created (media_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS nick_words (
  id   INT AUTO_INCREMENT PRIMARY KEY,
  kind ENUM('adj','noun') NOT NULL,
  word VARCHAR(12) NOT NULL,
  INDEX idx_nick_kind (kind)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comments (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  post_id     INT NOT NULL,
  user_id     INT NOT NULL,
  parent_id   INT NULL,
  anon_nick   VARCHAR(20) NOT NULL,
  body        TEXT NOT NULL,
  likes       INT NOT NULL DEFAULT 0,
  is_accepted TINYINT(1) NOT NULL DEFAULT 0,
  is_blind    TINYINT(1) NOT NULL DEFAULT 0,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_comments_post (post_id, created_at),
  FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS post_likes (
  post_id INT NOT NULL,
  user_id INT NOT NULL,
  PRIMARY KEY (post_id, user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reports (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  target_type ENUM('post','comment') NOT NULL,
  target_id   INT NOT NULL,
  user_id     INT NOT NULL,
  reason      VARCHAR(200) NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_reports_target (target_type, target_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS banners (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  image_url VARCHAR(300) NULL,
  link      VARCHAR(300) NULL,
  title     VARCHAR(120) NOT NULL,
  subtitle  VARCHAR(80) NULL,
  zone      ENUM('grid','slide') NOT NULL DEFAULT 'grid',
  sort      INT NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  start_at  DATETIME NULL,
  end_at    DATETIME NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- popular traffic (admin curated)
CREATE TABLE IF NOT EXISTS popular_categories (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  channel   ENUM('place','store','coupang') NOT NULL,
  name      VARCHAR(40) NOT NULL,
  sort      INT NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS popular_sets (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  category_id INT NOT NULL,
  rank        TINYINT NOT NULL,
  media_id    INT NOT NULL,
  note        VARCHAR(80) NULL,
  UNIQUE KEY uq_popular_rank (category_id, rank),
  FOREIGN KEY (category_id) REFERENCES popular_categories(id) ON DELETE CASCADE,
  FOREIGN KEY (media_id) REFERENCES media(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS popular_excludes (
  category_id INT NOT NULL,
  media_id    INT NOT NULL,
  PRIMARY KEY (category_id, media_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS popular_meta (
  category_id     INT PRIMARY KEY,
  show_weekly_cnt TINYINT(1) NOT NULL DEFAULT 1,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  updated_by      INT NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- agency
CREATE TABLE IF NOT EXISTS agency_requests (
  id                   INT AUTO_INCREMENT PRIMARY KEY,
  user_id              INT NOT NULL,
  anon_nick            VARCHAR(20) NOT NULL,
  channel              ENUM('place','store','coupang','multi') NOT NULL,
  industry             VARCHAR(40) NOT NULL,
  budget               ENUM('u30','30_100','100_300','o300','tbd') NOT NULL DEFAULT 'tbd',
  region               VARCHAR(40) NULL,
  body                 TEXT NOT NULL,
  contact              VARCHAR(40) NULL,
  status               ENUM('open','matched','closed') NOT NULL DEFAULT 'open',
  accepted_proposal_id INT NULL,
  views                INT NOT NULL DEFAULT 0,
  created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  closed_at            DATETIME NULL,
  INDEX idx_agency_req_status (status, created_at),
  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agency_proposals (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  request_id  INT NOT NULL,
  proposer_id INT NOT NULL,
  budget_plan TEXT NULL,
  plan        TEXT NULL,
  duration    VARCHAR(40) NULL,
  status      ENUM('sent','accepted','rejected') NOT NULL DEFAULT 'sent',
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_agency_prop_req (request_id),
  FOREIGN KEY (request_id) REFERENCES agency_requests(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agency_applies (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  user_id      INT NOT NULL,
  biz_no       VARCHAR(20) NOT NULL,
  biz_cert_url VARCHAR(300) NULL,
  status       ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_by  INT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;
