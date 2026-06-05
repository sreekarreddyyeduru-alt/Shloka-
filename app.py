"""app.py — SHLOKA Flask application"""
import os
from datetime import datetime, timezone
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, abort, send_from_directory)
from flask_login import (LoginManager, login_user, logout_user,
                         current_user, login_required)
from werkzeug.utils import secure_filename
from slugify import slugify

from engine import (db, User, Category, Chapter, Shloka,
                    Comment, Reaction, UserProgress, Bookmark, seed_database)


def create_app():
    app = Flask(__name__)

    app.config.update(
        SECRET_KEY="shloka-secret-change-in-production",
        SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(app.instance_path, "shloka.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=500 * 1024 * 1024,
        UPLOAD_VIDEO=os.path.join(app.root_path, "static", "uploads", "videos"),
        UPLOAD_THUMB=os.path.join(app.root_path, "static", "uploads", "thumbnails"),
    )

    os.makedirs(app.instance_path,          exist_ok=True)
    os.makedirs(app.config["UPLOAD_VIDEO"], exist_ok=True)
    os.makedirs(app.config["UPLOAD_THUMB"], exist_ok=True)

    db.init_app(app)

    lm = LoginManager(app)
    lm.login_view    = "signin"
    lm.login_message = "Please sign in to continue."

    @lm.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    with app.app_context():
        db.create_all()
        seed_database()

    # ── helpers ───────────────────────────────────────────────────────────────
    ALLOWED_VIDEO = {"mp4", "mov", "webm", "avi", "mkv"}
    ALLOWED_IMAGE = {"jpg", "jpeg", "png", "webp"}

    def ext(filename):
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    def unique_slug(base, Model, exclude_id=None):
        s, n = slugify(base), 1
        while True:
            q = Model.query.filter_by(slug=s)
            if exclude_id:
                q = q.filter(Model.id != exclude_id)
            if not q.first():
                return s
            s = f"{slugify(base)}-{n}"; n += 1

    def admin_required(f):
        @wraps(f)
        def dec(*a, **kw):
            if not current_user.is_authenticated or not current_user.is_admin:
                abort(403)
            return f(*a, **kw)
        return dec

    # ── context ───────────────────────────────────────────────────────────────
    @app.context_processor
    def inject():
        return dict(
            categories=Category.query.order_by(Category.sort_order).all(),
            now=datetime.now(timezone.utc),
        )

    # ═════════════════════════════════════════════════════════════════════════
    # PUBLIC
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/")
    def index():
        featured = (Shloka.query.filter_by(is_published=True, is_featured=True).first()
                    or Shloka.query.filter_by(is_published=True).order_by(Shloka.view_count.desc()).first())
        recent   = Shloka.query.filter_by(is_published=True).order_by(Shloka.published_at.desc()).limit(8).all()
        popular  = Shloka.query.filter_by(is_published=True).order_by(Shloka.view_count.desc()).limit(8).all()
        return render_template("index.html", featured=featured, recent=recent, popular=popular)

    @app.route("/category/<slug>")
    def category(slug):
        cat      = Category.query.filter_by(slug=slug).first_or_404()
        chapters = Chapter.query.filter_by(category_id=cat.id).order_by(Chapter.chapter_number).all()
        progress = {}
        if current_user.is_authenticated:
            for ch in chapters:
                ids  = [s.id for s in ch.shlokas if s.is_published]
                done = UserProgress.query.filter(
                    UserProgress.user_id  == current_user.id,
                    UserProgress.shloka_id.in_(ids),
                    UserProgress.is_completed == True,
                ).count() if ids else 0
                progress[ch.id] = {"done": done, "total": len(ids)}
        return render_template("category.html", cat=cat, chapters=chapters, progress=progress)

    @app.route("/watch/<slug>")
    def watch(slug):
        shloka = Shloka.query.filter_by(slug=slug, is_published=True).first_or_404()
        shloka.view_count += 1
        db.session.commit()

        related = (Shloka.query
                   .filter(Shloka.chapter_id == shloka.chapter_id,
                           Shloka.id != shloka.id,
                           Shloka.is_published == True)
                   .order_by(Shloka.sort_order).limit(10).all())
        if len(related) < 5:
            more = (Shloka.query
                    .filter(Shloka.category_id == shloka.category_id,
                            Shloka.id != shloka.id,
                            Shloka.is_published == True)
                    .order_by(Shloka.view_count.desc()).limit(10).all())
            seen = {r.id for r in related}
            related += [m for m in more if m.id not in seen]

        user_progress   = None
        user_bookmarked = False
        user_reaction   = None
        if current_user.is_authenticated:
            user_progress   = UserProgress.query.filter_by(user_id=current_user.id, shloka_id=shloka.id).first()
            user_bookmarked = Bookmark.query.filter_by(user_id=current_user.id, shloka_id=shloka.id).first() is not None
            user_reaction   = Reaction.query.filter_by(user_id=current_user.id, shloka_id=shloka.id).first()

        comments = (Comment.query
                    .filter_by(shloka_id=shloka.id, parent_comment_id=None)
                    .order_by(Comment.is_pinned.desc(), Comment.created_at.desc()).all())

        reactions = {rt: shloka.reaction_count(rt)
                     for rt in ("namaste", "love", "enlightened", "inspiring")}

        return render_template("watch.html",
                               shloka=shloka, related=related,
                               comments=comments, reactions=reactions,
                               user_progress=user_progress,
                               user_bookmarked=user_bookmarked,
                               user_reaction=user_reaction)

    @app.route("/search")
    def search():
        q       = request.args.get("q", "").strip()
        results = []
        if q:
            like    = f"%{q}%"
            results = (Shloka.query
                       .filter(Shloka.is_published == True,
                               db.or_(Shloka.title.ilike(like),
                                      Shloka.sanskrit_text.ilike(like),
                                      Shloka.translation_english.ilike(like),
                                      Shloka.tags.ilike(like),
                                      Shloka.transliteration.ilike(like)))
                       .order_by(Shloka.view_count.desc()).limit(30).all())
        return render_template("search.html", query=q, results=results)

    # ═════════════════════════════════════════════════════════════════════════
    # AUTH
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/signin", methods=["GET", "POST"])
    def signin():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            pw    = request.form.get("password", "")
            user  = User.query.filter_by(email=email).first()
            if user and user.check_password(pw):
                login_user(user, remember=True)
                return redirect(request.args.get("next") or url_for("index"))
            flash("Invalid email or password.", "error")
        return render_template("auth.html", mode="signin")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        if request.method == "POST":
            name  = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            pw    = request.form.get("password", "")
            if User.query.filter_by(email=email).first():
                flash("An account with that email already exists.", "error")
            elif len(pw) < 6:
                flash("Password must be at least 6 characters.", "error")
            else:
                base  = slugify(name)[:20] or email.split("@")[0]
                uname = base; n = 1
                while User.query.filter_by(username=uname).first():
                    uname = f"{base}{n}"; n += 1
                parts   = name.split()
                initials = ((parts[0][0] + parts[-1][0]) if len(parts) >= 2 else name[:2]).upper()
                user = User(email=email, username=uname,
                            display_name=name)
                user.set_password(pw)
                db.session.add(user)
                db.session.commit()
                login_user(user)
                flash("Welcome to SHLOKA! 🙏", "success")
                return redirect(url_for("index"))
        return render_template("auth.html", mode="signup")

    @app.route("/signout")
    @login_required
    def signout():
        logout_user()
        return redirect(url_for("index"))

    # ═════════════════════════════════════════════════════════════════════════
    # PROFILE
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/profile")
    @login_required
    def profile():
        prog_entries    = UserProgress.query.filter_by(user_id=current_user.id).all()
        bookmarks       = (Bookmark.query.filter_by(user_id=current_user.id)
                           .order_by(Bookmark.created_at.desc()).all())
        completed_count = sum(1 for p in prog_entries if p.is_completed)
        categories      = Category.query.all()
        cat_progress    = {}
        for cat in categories:
            ids  = [s.id for s in Shloka.query.filter_by(category_id=cat.id, is_published=True).all()]
            done = sum(1 for p in prog_entries if p.shloka_id in ids and p.is_completed)
            if ids:
                cat_progress[cat.id] = {"done": done, "total": len(ids)}
        return render_template("profile.html",
                               prog_entries=prog_entries,
                               completed_count=completed_count,
                               bookmarks=bookmarks,
                               cat_progress=cat_progress,
                               categories=categories)

    # ═════════════════════════════════════════════════════════════════════════
    # API
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/react/<int:sid>", methods=["POST"])
    @login_required
    def api_react(sid):
        shloka = db.session.get(Shloka, sid)
        if not shloka:
            return jsonify(ok=False), 404
        rtype   = (request.json or {}).get("type", "namaste")
        existing = Reaction.query.filter_by(shloka_id=sid, user_id=current_user.id,
                                            reaction_type=rtype).first()
        if existing:
            db.session.delete(existing); active = False
        else:
            Reaction.query.filter_by(shloka_id=sid, user_id=current_user.id).delete()
            db.session.add(Reaction(shloka_id=sid, user_id=current_user.id, reaction_type=rtype))
            active = True
        db.session.commit()
        counts = {rt: Reaction.query.filter_by(shloka_id=sid, reaction_type=rt).count()
                  for rt in ("namaste", "love", "enlightened", "inspiring")}
        return jsonify(ok=True, active=active, type=rtype, counts=counts)

    @app.route("/api/bookmark/<int:sid>", methods=["POST"])
    @login_required
    def api_bookmark(sid):
        shloka = db.session.get(Shloka, sid)
        if not shloka:
            return jsonify(ok=False), 404
        existing = Bookmark.query.filter_by(user_id=current_user.id, shloka_id=sid).first()
        if existing:
            db.session.delete(existing); bm = False
        else:
            db.session.add(Bookmark(user_id=current_user.id, shloka_id=sid)); bm = True
        db.session.commit()
        return jsonify(ok=True, bookmarked=bm)

    @app.route("/api/progress/<int:sid>", methods=["POST"])
    @login_required
    def api_progress(sid):
        pct   = int((request.json or {}).get("percent", 0))
        entry = UserProgress.query.filter_by(user_id=current_user.id, shloka_id=sid).first()
        if entry:
            entry.watch_percent = max(entry.watch_percent, pct)
            entry.last_watched  = datetime.now(timezone.utc)
            entry.watch_count  += 1
            if pct >= 80 and not entry.is_completed:
                entry.is_completed = True
                entry.completed_at = datetime.now(timezone.utc)
        else:
            entry = UserProgress(
                user_id=current_user.id, shloka_id=sid,
                watch_percent=pct,
                is_completed=(pct >= 80),
                completed_at=datetime.now(timezone.utc) if pct >= 80 else None,
            )
            db.session.add(entry)
        db.session.commit()
        return jsonify(ok=True, completed=entry.is_completed)

    @app.route("/api/comment/<int:sid>", methods=["POST"])
    @login_required
    def api_comment(sid):
        content = (request.json or {}).get("content", "").strip()
        if not content:
            return jsonify(ok=False, error="Empty"), 400
        c = Comment(shloka_id=sid, user_id=current_user.id, content=content)
        db.session.add(c); db.session.commit()
        return jsonify(ok=True, id=c.id, content=c.content,
                       author=current_user.display_name or current_user.username,
                       initials=current_user.get_initials(),
                       is_admin=current_user.is_admin)

    # ═════════════════════════════════════════════════════════════════════════
    # ADMIN
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/admin")
    @login_required
    @admin_required
    def admin_dashboard():
        total   = Shloka.query.count()
        pub     = Shloka.query.filter_by(is_published=True).count()
        views   = db.session.query(db.func.sum(Shloka.view_count)).scalar() or 0
        users   = User.query.filter_by(is_admin=False).count()
        comms   = Comment.query.count()
        recent  = Shloka.query.order_by(Shloka.created_at.desc()).limit(8).all()
        top     = Shloka.query.filter_by(is_published=True).order_by(Shloka.view_count.desc()).limit(5).all()
        r_comms = Comment.query.order_by(Comment.created_at.desc()).limit(5).all()
        return render_template("admin/dashboard.html",
                               total=total, pub=pub, views=views,
                               users=users, comms=comms,
                               recent=recent, top=top, r_comms=r_comms)

    @app.route("/admin/shlokas")
    @login_required
    @admin_required
    def admin_shlokas():
        shlokas = Shloka.query.order_by(Shloka.created_at.desc()).all()
        return render_template("admin/shlokas.html", shlokas=shlokas)

    @app.route("/admin/upload", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_upload():
        cats  = Category.query.order_by(Category.sort_order).all()
        chaps = Chapter.query.order_by(Chapter.chapter_number).all()
        if request.method == "POST":
            title   = request.form.get("title", "").strip()
            san     = request.form.get("sanskrit_text", "").strip()
            if not title or not san:
                flash("Title and Sanskrit text are required.", "error")
                return render_template("admin/upload.html", cats=cats, chaps=chaps)
            slug    = unique_slug(title, Shloka)
            cat_id  = request.form.get("category_id") or None
            ch_id   = request.form.get("chapter_id")  or None
            publish = request.form.get("publish") == "1"
            vid_f   = None; thm_f = None
            vf = request.files.get("video")
            if vf and vf.filename and ext(vf.filename) in ALLOWED_VIDEO:
                fname = secure_filename(f"{slug}.{ext(vf.filename)}")
                vf.save(os.path.join(app.config["UPLOAD_VIDEO"], fname))
                vid_f = fname
            tf = request.files.get("thumbnail")
            if tf and tf.filename and ext(tf.filename) in ALLOWED_IMAGE:
                fname = secure_filename(f"{slug}_thumb.{ext(tf.filename)}")
                tf.save(os.path.join(app.config["UPLOAD_THUMB"], fname))
                thm_f = fname
            s = Shloka(
                title=title, slug=slug,
                category_id=int(cat_id) if cat_id else None,
                chapter_id=int(ch_id)   if ch_id  else None,
                shloka_number=request.form.get("shloka_number",""),
                sanskrit_text=san,
                transliteration=request.form.get("transliteration",""),
                translation_english=request.form.get("translation_english",""),
                commentary=request.form.get("commentary",""),
                difficulty_level=request.form.get("difficulty_level","beginner"),
                tags=request.form.get("tags",""),
                duration_seconds=int(request.form.get("duration_seconds",0) or 0),
                video_filename=vid_f, thumbnail_filename=thm_f,
                is_published=publish, is_featured=request.form.get("featured")=="1",
                published_at=datetime.now(timezone.utc) if publish else None,
            )
            db.session.add(s); db.session.commit()
            flash(f"'{title}' {'published' if publish else 'saved as draft'}! 🎉", "success")
            return redirect(url_for("watch", slug=s.slug) if publish else url_for("admin_shlokas"))
        return render_template("admin/upload.html", cats=cats, chaps=chaps, shloka=None)

    @app.route("/admin/shlokas/<int:sid>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_edit(sid):
        shloka = db.session.get(Shloka, sid) or abort(404)
        cats   = Category.query.order_by(Category.sort_order).all()
        chaps  = Chapter.query.order_by(Chapter.chapter_number).all()
        if request.method == "POST":
            shloka.title               = request.form.get("title", shloka.title).strip()
            shloka.shloka_number       = request.form.get("shloka_number","")
            shloka.category_id         = int(request.form.get("category_id") or shloka.category_id)
            shloka.chapter_id          = int(request.form.get("chapter_id") or 0) or None
            shloka.sanskrit_text       = request.form.get("sanskrit_text","")
            shloka.transliteration     = request.form.get("transliteration","")
            shloka.translation_english = request.form.get("translation_english","")
            shloka.commentary          = request.form.get("commentary","")
            shloka.difficulty_level    = request.form.get("difficulty_level","beginner")
            shloka.tags                = request.form.get("tags","")
            shloka.duration_seconds    = int(request.form.get("duration_seconds",0) or 0)
            shloka.is_featured         = request.form.get("featured") == "1"
            pub = request.form.get("publish") == "1"
            if pub and not shloka.is_published:
                shloka.published_at = datetime.now(timezone.utc)
            shloka.is_published = pub
            vf = request.files.get("video")
            if vf and vf.filename and ext(vf.filename) in ALLOWED_VIDEO:
                fname = secure_filename(f"{shloka.slug}.{ext(vf.filename)}")
                vf.save(os.path.join(app.config["UPLOAD_VIDEO"], fname))
                shloka.video_filename = fname
            tf = request.files.get("thumbnail")
            if tf and tf.filename and ext(tf.filename) in ALLOWED_IMAGE:
                fname = secure_filename(f"{shloka.slug}_thumb.{ext(tf.filename)}")
                tf.save(os.path.join(app.config["UPLOAD_THUMB"], fname))
                shloka.thumbnail_filename = fname
            db.session.commit()
            flash("Shloka updated! ✓", "success")
            return redirect(url_for("watch", slug=shloka.slug))
        return render_template("admin/upload.html",
                               shloka=shloka, cats=cats, chaps=chaps, editing=True)

    @app.route("/admin/shlokas/<int:sid>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete(sid):
        s = db.session.get(Shloka, sid)
        if s:
            db.session.delete(s); db.session.commit()
            flash("Shloka deleted.", "success")
        return redirect(url_for("admin_shlokas"))

    @app.route("/admin/shlokas/<int:sid>/toggle", methods=["POST"])
    @login_required
    @admin_required
    def admin_toggle(sid):
        s = db.session.get(Shloka, sid)
        if s:
            s.is_published = not s.is_published
            if s.is_published:
                s.published_at = datetime.now(timezone.utc)
            db.session.commit()
        return redirect(url_for("admin_shlokas"))

    @app.route("/admin/categories", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_categories():
        if request.method == "POST":
            name = request.form.get("name","").strip()
            if name:
                c = Category(
                    name=name, slug=unique_slug(name, Category),
                    description=request.form.get("description",""),
                    color_accent=request.form.get("color_accent","#C8956C"),
                    color_bg=request.form.get("color_bg","#1E1309"),
                    icon=request.form.get("icon","📖"),
                )
                db.session.add(c); db.session.commit()
                flash(f"Category '{name}' created.", "success")
        return render_template("admin/categories.html",
                               categories=Category.query.order_by(Category.sort_order).all())

    @app.route("/admin/categories/<int:cid>/chapters", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_chapters(cid):
        cat = db.session.get(Category, cid) or abort(404)
        if request.method == "POST":
            title = request.form.get("title","").strip()
            num   = int(request.form.get("chapter_number", 1))
            if title:
                ch = Chapter(
                    category_id=cid,
                    chapter_number=num, title=title,
                    slug=unique_slug(f"{cat.slug}-ch-{num}", Chapter),
                    description=request.form.get("description",""),
                )
                db.session.add(ch); db.session.commit()
                flash(f"Chapter '{title}' added.", "success")
        chapters = Chapter.query.filter_by(category_id=cid).order_by(Chapter.chapter_number).all()
        return render_template("admin/chapters.html", cat=cat, chapters=chapters)

    @app.route("/admin/comments/<int:cid>/pin",    methods=["POST"])
    @login_required
    @admin_required
    def admin_pin(cid):
        c = db.session.get(Comment, cid)
        if c:
            c.is_pinned = not c.is_pinned; db.session.commit()
        return redirect(request.referrer or url_for("admin_dashboard"))

    @app.route("/admin/comments/<int:cid>/delete", methods=["POST"])
    @login_required
    def delete_comment(cid):
        c = db.session.get(Comment, cid)
        if c and (current_user.is_admin or c.user_id == current_user.id):
            slug = c.shloka.slug
            db.session.delete(c); db.session.commit()
            flash("Comment deleted.", "success")
            return redirect(url_for("watch", slug=slug))
        abort(403)

    # ── static video/thumb serving ────────────────────────────────────────────
    @app.route("/uploads/videos/<path:fn>")
    def serve_video(fn):
        return send_from_directory(app.config["UPLOAD_VIDEO"], fn)

    @app.route("/uploads/thumbnails/<path:fn>")
    def serve_thumb(fn):
        return send_from_directory(app.config["UPLOAD_THUMB"], fn)

    # ── error pages ───────────────────────────────────────────────────────────
    @app.errorhandler(403)
    def e403(e): return render_template("error.html", code=403, msg="Access Denied"), 403

    @app.errorhandler(404)
    def e404(e): return render_template("error.html", code=404, msg="Page Not Found"), 404

    return app
