"""engine.py — Database models and seed data for SHLOKA"""
import json
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from slugify import slugify

db = SQLAlchemy()


# ─── MODELS ───────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False)
    username      = db.Column(db.String(100), unique=True)
    display_name  = db.Column(db.String(200))
    bio           = db.Column(db.Text)
    password_hash = db.Column(db.String(256))
    is_admin      = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    comments   = db.relationship("Comment",      backref="author", lazy=True, cascade="all,delete-orphan")
    reactions  = db.relationship("Reaction",     backref="user",   lazy=True, cascade="all,delete-orphan")
    progress   = db.relationship("UserProgress", backref="user",   lazy=True, cascade="all,delete-orphan")
    bookmarks  = db.relationship("Bookmark",     backref="user",   lazy=True, cascade="all,delete-orphan")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def get_initials(self):
        name  = self.display_name or self.username or self.email
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return name[:2].upper()


class Category(db.Model):
    __tablename__ = "categories"
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False)
    slug         = db.Column(db.String(200), unique=True, nullable=False)
    description  = db.Column(db.Text)
    color_accent = db.Column(db.String(7),  default="#C8956C")
    color_bg     = db.Column(db.String(7),  default="#1E1309")
    icon         = db.Column(db.String(10), default="📖")
    sort_order   = db.Column(db.Integer,    default=0)

    chapters = db.relationship("Chapter", backref="category", lazy=True,
                               order_by="Chapter.chapter_number", cascade="all,delete-orphan")
    shlokas  = db.relationship("Shloka",  backref="category", lazy=True)

    @property
    def total_shlokas(self):
        return Shloka.query.filter_by(category_id=self.id, is_published=True).count()

    @property
    def total_chapters(self):
        return len(self.chapters)


class Chapter(db.Model):
    __tablename__ = "chapters"
    id             = db.Column(db.Integer, primary_key=True)
    category_id    = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    title          = db.Column(db.String(300), nullable=False)
    slug           = db.Column(db.String(300), unique=True, nullable=False)
    description    = db.Column(db.Text)
    chapter_number = db.Column(db.Integer, default=1)

    shlokas = db.relationship("Shloka", backref="chapter", lazy=True,
                              order_by="Shloka.sort_order", cascade="all,delete-orphan")

    @property
    def total_shlokas(self):
        return Shloka.query.filter_by(chapter_id=self.id, is_published=True).count()


class Shloka(db.Model):
    __tablename__ = "shlokas"
    id                  = db.Column(db.Integer, primary_key=True)
    title               = db.Column(db.String(500), nullable=False)
    slug                = db.Column(db.String(500), unique=True, nullable=False)
    category_id         = db.Column(db.Integer, db.ForeignKey("categories.id"))
    chapter_id          = db.Column(db.Integer, db.ForeignKey("chapters.id"))
    video_filename      = db.Column(db.String(500))
    thumbnail_filename  = db.Column(db.String(500))
    duration_seconds    = db.Column(db.Integer, default=0)
    shloka_number       = db.Column(db.String(50))
    sanskrit_text       = db.Column(db.Text, nullable=False)
    transliteration     = db.Column(db.Text)
    word_by_word        = db.Column(db.Text)
    translation_english = db.Column(db.Text)
    commentary          = db.Column(db.Text)
    difficulty_level    = db.Column(db.String(20), default="beginner")
    tags                = db.Column(db.String(500), default="")
    is_published        = db.Column(db.Boolean, default=False)
    is_featured         = db.Column(db.Boolean, default=False)
    published_at        = db.Column(db.DateTime)
    view_count          = db.Column(db.Integer, default=0)
    sort_order          = db.Column(db.Integer, default=0)
    created_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    comments  = db.relationship("Comment",      backref="shloka", lazy=True,
                                order_by="Comment.created_at.desc()", cascade="all,delete-orphan")
    reactions = db.relationship("Reaction",     backref="shloka", lazy=True, cascade="all,delete-orphan")
    progress  = db.relationship("UserProgress", backref="shloka", lazy=True, cascade="all,delete-orphan")
    bookmarks = db.relationship("Bookmark",     backref="shloka", lazy=True, cascade="all,delete-orphan")

    def get_word_by_word(self):
        if not self.word_by_word:
            return []
        try:
            return json.loads(self.word_by_word)
        except Exception:
            return []

    def get_tags(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    def duration_str(self):
        s = self.duration_seconds or 0
        return f"{s // 60}:{s % 60:02d}"

    def reaction_count(self, rtype):
        return Reaction.query.filter_by(shloka_id=self.id, reaction_type=rtype).count()


class Comment(db.Model):
    __tablename__ = "comments"
    id                = db.Column(db.Integer, primary_key=True)
    shloka_id         = db.Column(db.Integer, db.ForeignKey("shlokas.id"),  nullable=False)
    user_id           = db.Column(db.Integer, db.ForeignKey("users.id"),    nullable=False)
    content           = db.Column(db.Text, nullable=False)
    is_pinned         = db.Column(db.Boolean, default=False)
    parent_comment_id = db.Column(db.Integer, db.ForeignKey("comments.id"))
    created_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    replies           = db.relationship("Comment",
                                        backref=db.backref("parent", remote_side=[id]),
                                        lazy=True, cascade="all,delete-orphan")


class Reaction(db.Model):
    __tablename__  = "reactions"
    id             = db.Column(db.Integer, primary_key=True)
    shloka_id      = db.Column(db.Integer, db.ForeignKey("shlokas.id"), nullable=False)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"),   nullable=False)
    reaction_type  = db.Column(db.String(50), nullable=False)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint("shloka_id", "user_id", "reaction_type"),)


class UserProgress(db.Model):
    __tablename__  = "user_progress"
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"),   nullable=False)
    shloka_id      = db.Column(db.Integer, db.ForeignKey("shlokas.id"), nullable=False)
    watch_percent  = db.Column(db.Integer, default=0)
    is_completed   = db.Column(db.Boolean, default=False)
    completed_at   = db.Column(db.DateTime)
    last_watched   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    watch_count    = db.Column(db.Integer, default=1)
    __table_args__ = (db.UniqueConstraint("user_id", "shloka_id"),)


class Bookmark(db.Model):
    __tablename__  = "bookmarks"
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"),   nullable=False)
    shloka_id      = db.Column(db.Integer, db.ForeignKey("shlokas.id"), nullable=False)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint("user_id", "shloka_id"),)


# ─── SEED DATA ────────────────────────────────────────────────────────────────

def seed_database():
    if Category.query.first():
        return  # already seeded

    # ── Users ──────────────────────────────────────────────────────────────────
    admin = User(email="admin@shloka.app", username="creator",
                 display_name="Shloka Creator", is_admin=True)
    admin.set_password("admin123")
    db.session.add(admin)

    demo = User(email="demo@shloka.app", username="sreekar",
                display_name="Sreekar")
    demo.set_password("demo123")
    db.session.add(demo)
    db.session.flush()

    # ── Categories ─────────────────────────────────────────────────────────────
    cats_raw = [
        ("Bhagavad Gita",   "bhagavad-gita",  "#C8956C", "#1E1309", "📖",
         "The eternal dialogue between Arjuna and Lord Krishna on the battlefield of Kurukshetra."),
        ("Hanuman Chalisa", "hanuman-chalisa", "#D4700A", "#1A0C00", "🙏",
         "Tulsidas's 40-verse devotional hymn in praise of Lord Hanuman."),
        ("Ramayana",        "ramayana",        "#7B9E3E", "#0E1500", "🌺",
         "Valmiki's immortal epic — the journey of Rama, Sita, and the victory of dharma."),
        ("Upanishads",      "upanishads",      "#5B8ED6", "#0A1220", "🕉️",
         "Ancient philosophical dialogues on the nature of Brahman, Atman, and liberation."),
    ]
    cats = {}
    for name, slug, color, bg, icon, desc in cats_raw:
        c = Category(name=name, slug=slug, color_accent=color,
                     color_bg=bg, icon=icon, description=desc)
        db.session.add(c)
        cats[slug] = c
    db.session.flush()

    # ── Chapters ───────────────────────────────────────────────────────────────
    bg_ch_raw = [
        (1,  "Arjuna's Dilemma",            "bg-ch-1"),
        (2,  "Sankhya Yoga",                "bg-ch-2"),
        (3,  "Karma Yoga",                  "bg-ch-3"),
        (4,  "Jnana Karma Sanyasa Yoga",    "bg-ch-4"),
        (18, "Liberation Through Renunciation", "bg-ch-18"),
    ]
    bg_chs = {}
    for num, title, slug in bg_ch_raw:
        ch = Chapter(category_id=cats["bhagavad-gita"].id,
                     title=title, slug=slug, chapter_number=num)
        db.session.add(ch)
        bg_chs[num] = ch

    hc_ch = Chapter(category_id=cats["hanuman-chalisa"].id,
                    title="Hanuman Chalisa", slug="hc-main", chapter_number=1)
    db.session.add(hc_ch)
    db.session.flush()

    # ── Shlokas ────────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)

    shlokas_raw = [
        dict(
            title="BG 1.1 — Dhritarashtra's Question",
            slug="bg-1-1", cat="bhagavad-gita", ch_num=1, num="1.1",
            san="धृतराष्ट्र उवाच।\nधर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः।\nमामकाः पाण्डवाश्चैव किमकुर्वत सञ्जय॥",
            tr="dhṛtarāṣṭra uvāca | dharma-kṣetre kuru-kṣetre samavetā yuyutsavaḥ | māmakāḥ pāṇḍavāś caiva kim akurvata sañjaya ||",
            en="Dhritarashtra said: O Sanjaya, after assembling in the place of pilgrimage at Kurukshetra, what did my sons and the sons of Pandu do, being desirous to fight?",
            comm="The Gita opens with the blind king asking his minister to narrate events on the battlefield. The word 'dharma-kshetra' immediately establishes that this is not just a physical conflict but a moral and spiritual one.",
            diff="beginner", tags="opening,kurukshetra,dharma", dur=252, featured=False,
        ),
        dict(
            title="BG 2.47 — Nishkama Karma",
            slug="bg-2-47", cat="bhagavad-gita", ch_num=2, num="2.47",
            san="कर्मण्येवाधिकारस्ते मा फलेषु कदाचन।\nमा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि॥",
            tr="karmaṇy evādhikāras te mā phaleṣu kadācana | mā karma-phala-hetur bhūr mā te saṅgo'stv akarmaṇi ||",
            en="You have a right to perform your prescribed duties, but you are not entitled to the fruits of your actions. Never consider yourself the cause of the results of your activities, and never be attached to not doing your duty.",
            comm="This is the heart of Karma Yoga. Krishna gives three precise instructions: act without craving results; do not become the ego-driven cause of results; do not use renunciation of results as an excuse for inaction. This teaching liberates from anxiety while enabling focused, sustained action.",
            diff="beginner", tags="karma,dharma,detachment,nishkama,yoga,famous", dur=272, featured=True,
            wbw=[
                {"word":"कर्मणि","translit":"karmaṇi","meaning":"in action / in duties"},
                {"word":"एव","translit":"eva","meaning":"certainly / indeed"},
                {"word":"अधिकारः","translit":"adhikāraḥ","meaning":"right / authority"},
                {"word":"ते","translit":"te","meaning":"your"},
                {"word":"मा","translit":"mā","meaning":"never / not"},
                {"word":"फलेषु","translit":"phaleṣu","meaning":"in the fruits / results"},
                {"word":"कदाचन","translit":"kadācana","meaning":"at any time"},
            ],
        ),
        dict(
            title="BG 2.20 — The Eternal Soul",
            slug="bg-2-20", cat="bhagavad-gita", ch_num=2, num="2.20",
            san="न जायते म्रियते वा कदाचिन्\nनायं भूत्वा भविता वा न भूयः।\nअजो नित्यः शाश्वतोऽयं पुराणो\nन हन्यते हन्यमाने शरीरे॥",
            tr="na jāyate mriyate vā kadācin nāyaṃ bhūtvā bhavitā vā na bhūyaḥ | ajo nityaḥ śāśvato'yaṃ purāṇo na hanyate hanyamāne śarīre ||",
            en="The soul is never born nor does it die. It has not come into being, does not come into being, and will not come into being. It is unborn, eternal, ever-existing, and ancient. It is not slain when the body is slain.",
            comm="Krishna teaches the fundamental Vedantic truth about the Atman. If the soul is eternal and indestructible, there is no cause for grief over death. The soul cannot be cut by weapons, burned by fire, wetted by water, or dried by wind.",
            diff="intermediate", tags="atman,soul,eternal,metaphysics", dur=318, featured=False,
        ),
        dict(
            title="BG 4.7 — Whenever Dharma Declines",
            slug="bg-4-7", cat="bhagavad-gita", ch_num=4, num="4.7",
            san="यदा यदा हि धर्मस्य ग्लानिर्भवति भारत।\nअभ्युत्थानमधर्मस्य तदात्मानं सृजाम्यहम्॥",
            tr="yadā yadā hi dharmasya glānir bhavati bhārata | abhyutthānam adharmasya tadātmānaṃ sṛjāmy aham ||",
            en="Whenever there is a decline in righteousness and a rise in unrighteousness, O Arjuna, at that time I manifest myself on earth.",
            comm="Krishna's declaration of the divine principle of avatara — the Divine descends whenever the balance between dharma and adharma tips dangerously. This is not a one-time event but a recurring cosmic law.",
            diff="beginner", tags="avatar,dharma,krishna,incarnation,famous", dur=290, featured=False,
        ),
        dict(
            title="BG 18.66 — The Final Teaching",
            slug="bg-18-66", cat="bhagavad-gita", ch_num=18, num="18.66",
            san="सर्वधर्मान्परित्यज्य मामेकं शरणं व्रज।\nअहं त्वा सर्वपापेभ्यो मोक्षयिष्यामि मा शुचः॥",
            tr="sarva-dharmān parityajya mām ekaṃ śaraṇaṃ vraja | ahaṃ tvā sarva-pāpebhyo mokṣayiṣyāmi mā śucaḥ ||",
            en="Abandon all varieties of religion and simply surrender unto Me. I shall deliver you from all sinful reactions; do not fear.",
            comm="This is the charamashloka — the ultimate verse of the Gita. After 18 chapters of elaborate philosophy, Krishna distills everything into one instruction: surrender. Not to any rule or ritual, but to the Divine itself.",
            diff="advanced", tags="surrender,moksha,liberation,bhakti,charamashloka,famous", dur=390, featured=False,
        ),
        dict(
            title="HC Doha 1 — Opening Invocation",
            slug="hc-doha-1", cat="hanuman-chalisa", ch_num=1, num="Doha 1",
            san="श्रीगुरु चरन सरोज रज निज मनु मुकुरु सुधारि।\nबरनउँ रघुबर बिमल जसु जो दायकु फल चारि॥",
            tr="śrī guru carana saroja raja nija manu mukuru sudhāri | baranauṃ raghubara bimala jasu jo dāyaku phala cāri ||",
            en="After purifying the mirror of my mind with the pollen dust of the holy Guru's lotus feet, I narrate the pure glory of Raghuvara which bestows all four fruits of life.",
            comm="Tulsidas begins with a traditional invocation — cleaning the mind with the grace of the Guru before singing divine praise. The four fruits refer to Dharma, Artha, Kama, and Moksha — the four goals of human life.",
            diff="beginner", tags="hanuman,guru,rama,devotion,opening", dur=165, featured=False,
        ),
        dict(
            title="HC Chaupai 4 — Grant Strength and Wisdom",
            slug="hc-ch-4", cat="hanuman-chalisa", ch_num=1, num="Chaupai 4",
            san="बुद्धिहीन तनु जानिके सुमिरौं पवन-कुमार।\nबल बुधि बिद्या देहु मोहिं हरहु कलेस बिकार॥",
            tr="buddhihīna tanu jānike sumiraun pavana-kumāra | bala budhi bidyā dehu mohin harahu kalesa bikāra ||",
            en="Knowing myself to be without intelligence, I remember you, O Son of the Wind. Grant me strength, wisdom, and knowledge, and remove my sorrows and faults.",
            comm="One of the most honest prayers in devotional literature. The devotee acknowledges limitations openly and approaches Hanuman not with pride but complete surrender. Hanuman is invoked as Pavan Kumar — Son of the Wind God.",
            diff="beginner", tags="hanuman,wisdom,prayer,strength,humility", dur=195, featured=False,
        ),
    ]

    for raw in shlokas_raw:
        cat  = cats[raw["cat"]]
        ch   = bg_chs.get(raw["ch_num"]) if raw["cat"] == "bhagavad-gita" else hc_ch
        wbw  = json.dumps(raw.get("wbw", [])) if raw.get("wbw") else None
        s    = Shloka(
            title=raw["title"], slug=raw["slug"],
            category_id=cat.id, chapter_id=ch.id if ch else None,
            shloka_number=raw["num"],
            sanskrit_text=raw["san"], transliteration=raw["tr"],
            word_by_word=wbw,
            translation_english=raw["en"], commentary=raw["comm"],
            difficulty_level=raw["diff"], tags=raw["tags"],
            duration_seconds=raw["dur"],
            is_published=True, is_featured=raw["featured"],
            published_at=now, view_count=0,
        )
        db.session.add(s)

    db.session.flush()

    # Sample progress for demo user
    bg247 = Shloka.query.filter_by(slug="bg-2-47").first()
    if bg247:
        db.session.add(UserProgress(
            user_id=demo.id, shloka_id=bg247.id,
            watch_percent=100, is_completed=True,
            completed_at=now, watch_count=3,
        ))

    db.session.commit()
    print("  Database seeded with 7 shlokas across 4 scriptures.")
