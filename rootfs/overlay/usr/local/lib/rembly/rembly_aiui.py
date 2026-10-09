"""rembly_aiui - the AI parts of Rembly Code (GTK): settings (your key or a local server), the chat panel with streaming answers, "edit the selection with AI" (Ctrl+K)
with a diff preview, applying <file> answers with backups, and the project wizard where the AI plans a project and writes its files.
Nothing an answer proposes happens by itself: files are previewed and written only after you confirm, commands need an explicit tick and a deny-list check.
The host window (Code) provides: current(), folder, open_file(path), set_folder(path), term, term_run(cmd), flash(text), msg(text)."""
import difflib, os, subprocess, threading
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango
import remblyui as ui
import rembly_ai as ai
import rembly_term as rt

QUICK = [('Объяснить', 'Объясни, что делает этот код, простыми словами и по шагам. Отметь возможные проблемы.'),
         ('Исправить', 'Найди и исправь ошибки в этом коде. Верни исправленный код целиком в одном блоке и кратко объясни, что было не так.'),
         ('Тесты', 'Напиши тесты для этого кода (стандартными средствами языка, например unittest для Python). Верни их файлом в формате <file path="...">.'),
         ('Оптимизировать', 'Оптимизируй этот код для слабого планшета (2 ГБ ОЗУ), не меняя поведения. Верни улучшенный код одним блоком и перечисли изменения.')]
EXAMPLES = ['Сайт-визитка на HTML и CSS с тёмной темой', 'Консольная программа на Python: заметки с поиском, данные в JSON', 'Игра «Змейка» на Python (pygame)', 'REST API на Flask с одной таблицей SQLite',
            'Программа на C с CMake: чтение CSV и статистика', 'Telegram-бот на Python (библиотека requests, без лишних зависимостей)', 'Скрипт на bash: резервное копирование папки с архивом по дате']
STACKS = [('auto', 'Авто (выберет ИИ)'), ('python', 'Python 3.8'), ('node', 'JavaScript / Node.js 10'), ('web', 'Веб: HTML + CSS + JS'), ('c', 'C (gcc, CMake или Makefile)'), ('cpp', 'C++ (g++, CMake)'),
          ('go', 'Go'), ('bash', 'Bash')]


def run_thread(fn, done=None):
    """fn() in a thread; done(result, error_text) on the GTK thread"""
    def work():
        try: r, e = fn(), None
        except ai.AIError as ex: r, e = None, str(ex)
        except Exception as ex: r, e = None, '%s: %s' % (type(ex).__name__, ex)
        if done: GLib.idle_add(lambda: (done(r, e), False)[1])
    threading.Thread(target=work, daemon=True).start()


def dlg(parent, title, size=None):
    d = Gtk.Dialog(title=title, transient_for=parent, modal=True); ui.style_app(d)
    if size: d.set_default_size(min(size[0], ui.screen_size()[0] - 20), min(size[1], ui.screen_size()[1] - 100))
    return d


def entry(text='', ph='', hidden=False):
    e = Gtk.Entry(); e.set_text(text); e.set_hexpand(True)
    if ph: e.set_placeholder_text(ph)
    if hidden: e.set_visibility(False)
    e.connect('focus-in-event', lambda *_: ui.osk(True)); return e


def confirm_host(win, cfg):
    """first use with a remote server: say plainly where the code goes. Local/private servers need no question."""
    h = ai.host_of(cfg)
    if ai.is_local(cfg) or h in cfg.get('accepted_hosts', []): return True
    d = Gtk.MessageDialog(transient_for=win, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
                          text='Отправлять код и вопросы на сервер %s?\n\nСодержимое текущего файла, выделенный код и ваши вопросы уходят этому провайдеру по интернету (файлы с ключами и паролями не включаются). Вы можете выключить контекст в панели ИИ.' % h)
    ui.style_app(d); r = d.run(); d.destroy()
    if r != Gtk.ResponseType.YES: return False
    cfg['accepted_hosts'] = list(cfg.get('accepted_hosts', [])) + [h]; ai.save(cfg); return True


# ---------------------------------------------------------------- settings
class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title='ИИ: ключ или локальный сервер', transient_for=parent, modal=True); ui.style_app(self); self.set_default_size(min(700, ui.screen_size()[0] - 20), min(620, ui.screen_size()[1] - 100))
        self.add_buttons('Отмена', Gtk.ResponseType.CANCEL, 'Сохранить', Gtk.ResponseType.OK); self.cfg = ai.load()
        sc = Gtk.ScrolledWindow(); sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); self.get_content_area().pack_start(sc, True, True, 0)
        g = Gtk.Grid(row_spacing=8, column_spacing=12); g.set_border_width(12); sc.add(g); self.n = 0; self.g = g
        self.preset = Gtk.ComboBoxText(); [self.preset.append(p['id'], p['title']) for p in ai.PRESETS]; self.preset.set_active_id(self.cfg.get('provider') if any(p['id'] == self.cfg.get('provider') for p in ai.PRESETS) else 'custom')
        self.note = Gtk.Label(label='', xalign=0); self.note.set_line_wrap(True); self.note.get_style_context().add_class('small')
        self.endpoint = entry(self.cfg['endpoint'], 'https://…/v1'); self.key = entry(self.cfg['key'], 'ключ (для локального сервера пусто)', hidden=True)
        show = Gtk.CheckButton(label='показать ключ'); show.connect('toggled', lambda w: self.key.set_visibility(w.get_active()))
        self.model = Gtk.ComboBoxText.new_with_entry(); self.model.get_child().set_text(self.cfg['model']); self.model.get_child().connect('focus-in-event', lambda *_: ui.osk(True))
        lb = Gtk.Button(label='Список моделей'); lb.connect('clicked', lambda _b: self.list_models()); mrow = Gtk.Box(spacing=8); mrow.pack_start(self.model, True, True, 0); mrow.pack_start(lb, False, False, 0)
        self.maxtok = Gtk.SpinButton.new_with_range(256, 16000, 128); self.maxtok.set_value(int(self.cfg.get('max_tokens', 2048)))
        self.timeout = Gtk.SpinButton.new_with_range(0, 900, 10); self.timeout.set_value(int(self.cfg.get('timeout') or 0))
        self.temp = Gtk.SpinButton.new_with_range(0, 1.5, 0.1); self.temp.set_digits(1); self.temp.set_value(float(self.cfg.get('temperature', 0.2)))
        self.row('Поставщик', self.preset); self.row('', self.note); self.row('Адрес сервера (endpoint)', self.endpoint); self.row('Ключ API', self.key); self.row('', show)
        self.row('Модель', mrow, 'Имя модели — такое, как его знает сервер. Кнопка «Список моделей» спросит у сервера, что у него есть.')
        self.row('Макс. токенов ответа', self.maxtok, 'Для создания проектов лучше 4000 и больше: ответ не должен обрываться.')
        self.row('Таймаут, сек (0 — авто)', self.timeout, 'Локальной модели на слабом железе нужно больше времени на первый ответ.'); self.row('Температура', self.temp)
        info = Gtk.Label(label='Ключ хранится на планшете в файле ~/.config/rembly/ai.json (доступ только владельцу), в открытом виде: системного хранилища паролей здесь нет. '
                               'Ключ отправляется только на адрес, который вы указали выше. Тот же ключ использует команда rembly-ai (разбор ошибок).', xalign=0)
        info.set_line_wrap(True); info.get_style_context().add_class('small'); self.row('', info)
        self.test_btn = Gtk.Button(label='Проверить связь'); self.test_btn.connect('clicked', lambda _b: self.test()); self.result = Gtk.Label(label='', xalign=0); self.result.set_line_wrap(True)
        tr = Gtk.Box(spacing=8); tr.pack_start(self.test_btn, False, False, 0); self.row('', tr); self.row('', self.result)
        self.preset.connect('changed', lambda *_: self.on_preset(True)); self.on_preset(False); self.show_all()

    def row(self, label, w, tip=None):
        if label: l = Gtk.Label(label=label, xalign=0); self.g.attach(l, 0, self.n, 1, 1)
        self.g.attach(w, 1, self.n, 1, 1); self.n += 1
        if tip: t = Gtk.Label(label=tip, xalign=0); t.set_line_wrap(True); t.get_style_context().add_class('small'); self.g.attach(t, 1, self.n, 1, 1); self.n += 1

    def preset_data(self):
        return next((p for p in ai.PRESETS if p['id'] == self.preset.get_active_id()), ai.PRESETS[-1])

    def on_preset(self, fill):
        p = self.preset_data(); self.note.set_text(p['note'])
        if fill and p['id'] != 'custom':
            self.endpoint.set_text(p['endpoint']); self.model.get_child().set_text(p['model'])
            if not p['key']: self.key.set_text('')

    def current(self):
        p = self.preset_data(); c = dict(self.cfg)
        c.update(provider=p['id'], kind=p['kind'], endpoint=self.endpoint.get_text().strip(), key=self.key.get_text().strip(), model=self.model.get_child().get_text().strip(),
                 max_tokens=int(self.maxtok.get_value()), timeout=int(self.timeout.get_value()), temperature=round(self.temp.get_value(), 1))
        return c

    def test(self):
        c = self.current(); self.result.set_text('Проверяю…'); self.test_btn.set_sensitive(False)
        def done(r, e):
            self.test_btn.set_sensitive(True)
            if e: self.result.set_text('✖ ' + e); return
            ok, txt, sec = r
            self.result.set_text(('✔ Связь есть, модель ответила за %.1f с: «%s»' % (sec, txt)) if ok else ('✖ ' + txt))
        run_thread(lambda: ai.test_connection(c), done)

    def list_models(self):
        c = self.current(); self.result.set_text('Спрашиваю у сервера список моделей…')
        def done(r, e):
            if e: self.result.set_text('✖ ' + e); return
            self.model.remove_all(); [self.model.append_text(m) for m in r]; self.result.set_text('✔ Моделей: %d. Выберите в списке справа от поля модели.' % len(r))
            if r and not self.model.get_child().get_text(): self.model.set_active(0)
        run_thread(lambda: ai.Client(c).list_models(), done)

    def save(self):
        ai.save(self.current())


def open_settings(win):
    d = SettingsDialog(win)
    while True:
        r = d.run()
        if r != Gtk.ResponseType.OK: break
        c = d.current()
        if not c['endpoint'] or not c['model']: d.result.set_text('✖ Заполните адрес сервера и модель.'); continue
        d.save(); break
    d.destroy(); return r == Gtk.ResponseType.OK


# ---------------------------------------------------------------- file preview / apply
class ApplyFilesDialog(Gtk.Dialog):
    """list of files an answer wants to write; every file can be unticked; existing files are shown as a diff and are copied to .rembly-ai-backup first"""
    def __init__(self, parent, root, files):
        super().__init__(title='Файлы от ИИ', transient_for=parent, modal=True); ui.style_app(self); self.set_default_size(min(980, ui.screen_size()[0] - 20), min(620, ui.screen_size()[1] - 100))
        self.add_buttons('Отмена', Gtk.ResponseType.CANCEL, 'Записать отмеченные', Gtk.ResponseType.OK); self.root = root
        self.ok, self.bad = ai.check_files(files, root)
        box = self.get_content_area(); box.set_border_width(10); box.set_spacing(8)
        head = Gtk.Label(label='Папка: %s\nФайлы записываются только после вашего подтверждения. Существующие файлы сначала копируются в .rembly-ai-backup.' % root, xalign=0); head.set_line_wrap(True); box.pack_start(head, False, False, 0)
        self.store = Gtk.ListStore(bool, str, str)
        for rel, _c, exists in self.ok: self.store.append([True, rel, 'изменится (есть копия)' if exists else 'новый'])
        tv = Gtk.TreeView(model=self.store); tv.set_headers_visible(False)
        r = Gtk.CellRendererToggle(); r.set_property('activatable', True); r.connect('toggled', lambda w, p: self.store.__setitem__(p, [not self.store[p][0], self.store[p][1], self.store[p][2]])); tv.append_column(Gtk.TreeViewColumn('', r, active=0))
        t = Gtk.CellRendererText(); t.set_property('ypad', 8); tv.append_column(Gtk.TreeViewColumn('', t, text=1)); t2 = Gtk.CellRendererText(); t2.set_property('foreground', '#bdbdbd'); tv.append_column(Gtk.TreeViewColumn('', t2, text=2))
        tv.get_selection().connect('changed', self.preview); sc = Gtk.ScrolledWindow(); sc.add(tv); sc.set_size_request(340, -1)
        self.pv = Gtk.TextView(); self.pv.set_editable(False); self.pv.get_style_context().add_class('mono'); self.pv.set_wrap_mode(Gtk.WrapMode.NONE); psc = Gtk.ScrolledWindow(); psc.add(self.pv)
        pan = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL); pan.pack1(sc, False, False); pan.pack2(psc, True, False); box.pack_start(pan, True, True, 0)
        if self.bad:
            warn = Gtk.Label(label='Пропущено (небезопасно или недопустимо): ' + '; '.join('%s — %s' % (p, why) for p, why in self.bad[:6]), xalign=0); warn.set_line_wrap(True); box.pack_start(warn, False, False, 0)
        self.show_all()
        if len(self.store): tv.get_selection().select_path(Gtk.TreePath(0))

    def preview(self, sel):
        m, it = sel.get_selected()
        if it is None: return
        rel = m[it][1]; new = next(c for r, c, _e in self.ok if r == rel); buf = self.pv.get_buffer(); buf.set_text(''); path = os.path.join(self.root, rel)
        if os.path.exists(path):
            try: old = open(path, errors='replace').read()
            except OSError: old = ''
            fill_diff(buf, old, new)
        else: buf.set_text(new[:20000])

    def selected(self):
        pick = {row[1] for row in self.store if row[0]}
        return [(rel, c) for rel, c, _e in self.ok if rel in pick]


DIFF_COLORS = {'add': '#7dff9b', 'del': '#ff8c8c', 'hdr': '#9ec7ff'}


def fill_diff(buf, old, new):
    """unified diff of old/new into a TextBuffer: green added lines, red removed ones"""
    buf.set_text('')
    for name, col in DIFF_COLORS.items():
        if buf.get_tag_table().lookup(name) is None: buf.create_tag(name, foreground=col)
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), 'было', 'стало', lineterm='', n=3))
    if not lines: buf.set_text('(без изменений)'); return
    for l in lines:
        tag = 'add' if l.startswith('+') and not l.startswith('+++') else 'del' if l.startswith('-') and not l.startswith('---') else 'hdr' if l.startswith(('@@', '---', '+++')) else None
        if tag: buf.insert_with_tags_by_name(buf.get_end_iter(), l + '\n', tag)
        else: buf.insert(buf.get_end_iter(), l + '\n')


def apply_files(win, files, root=None):
    """preview + write; returns the list of written relative paths"""
    root = root or win.folder
    if not os.path.isdir(root): win.msg('Сначала откройте папку проекта.'); return []
    d = ApplyFilesDialog(win, root, files)
    if not len(d.store) and d.bad:
        d.destroy(); win.msg('ИИ предложил только недопустимые пути; ничего не записано.'); return []
    r = d.run(); sel = d.selected() if r == Gtk.ResponseType.OK else []; d.destroy()
    if not sel: return []
    done = ai.write_files(root, sel, os.path.join(root, '.rembly-ai-backup'))
    win.set_folder(root); win.flash('записано файлов: %d' % len(done))
    if done: win.open_file(os.path.join(root, done[0]))
    return done


# ---------------------------------------------------------------- edit the selection (Ctrl+K)
def ai_edit(win):
    doc = win.current()
    if doc is None: return
    cfg = ai.load()
    if not ai.configured(cfg):
        if not open_settings(win): return
        cfg = ai.load()
    if not confirm_host(win, cfg): return
    buf = doc.buf; has_sel = buf.get_has_selection()
    if has_sel: a, b = buf.get_selection_bounds()
    else: a, b = buf.get_start_iter(), buf.get_end_iter()
    old = buf.get_text(a, b, True)
    if not has_sel and len(old) > 20000: win.msg('Файл большой: выделите фрагмент, который нужно изменить.'); return
    if ai.SENSITIVE_NAMES.search(doc.path or ''): win.msg('Этот файл похож на секретный (ключи, пароли): в ИИ он не отправляется.'); return
    sm, em = buf.create_mark(None, a, True), buf.create_mark(None, b, False)
    d = dlg(win, 'ИИ: изменить %s' % ('выделенное' if has_sel else 'весь файл'), (900, 640)); d.add_buttons('Закрыть', Gtk.ResponseType.CLOSE)
    box = d.get_content_area(); box.set_border_width(10); box.set_spacing(8)
    ins = entry('', 'что сделать, например: добавь проверку ошибок / переведи комментарии на английский / замени цикл на генератор'); box.pack_start(ins, False, False, 0)
    row = Gtk.Box(spacing=8); go = Gtk.Button(label='Выполнить'); stop = Gtk.Button(label='Стоп'); stop.set_sensitive(False); apply_b = Gtk.Button(label='Применить'); apply_b.set_sensitive(False)
    status = Gtk.Label(label='', xalign=0); [row.pack_start(w, False, False, 0) for w in (go, stop, apply_b)]; row.pack_start(status, True, True, 8); box.pack_start(row, False, False, 0)
    tv = Gtk.TextView(); tv.set_editable(False); tv.get_style_context().add_class('mono'); sc = Gtk.ScrolledWindow(); sc.add(tv); box.pack_start(sc, True, True, 0)
    bf = tv.get_buffer(); bf.set_text('Опишите изменение и нажмите «Выполнить». Результат будет показан как разница; в файл он попадёт только после «Применить», одним шагом отмены (Ctrl+Z).')
    st = {'new': None, 'client': None}

    def finish(r, e):
        go.set_sensitive(True); stop.set_sensitive(False)
        if e: status.set_text('✖ ' + e); return
        new = ai.first_code(r or '')
        if not new.strip(): status.set_text('✖ ИИ вернул пустой ответ'); return
        st['new'] = new; fill_diff(bf, old, new); status.set_text('Готово. Проверьте разницу и нажмите «Применить».'); apply_b.set_sensitive(True)

    def run(*_):
        text = ins.get_text().strip()
        if not text: status.set_text('Напишите, что нужно сделать.'); return
        go.set_sensitive(False); stop.set_sensitive(True); apply_b.set_sensitive(False); status.set_text('ИИ работает…'); cl = st['client'] = ai.Client(cfg); got = [0]
        lang = doc.lang
        user = 'File: %s (%s)\nInstruction: %s\n\n%s:\n```\n%s\n```' % (os.path.basename(doc.path or 'untitled'), lang, text, 'Selected code' if has_sel else 'Whole file', old)
        def prog(p): got[0] += len(p); GLib.idle_add(status.set_text, 'ИИ пишет… получено %d символов' % got[0])
        run_thread(lambda: cl.chat([{'role': 'user', 'content': user}], system=ai.SYSTEM_EDIT, max_tokens=max(int(cfg.get('max_tokens', 2048)), 3000), on_text=prog), finish)

    def do_apply(*_):
        new = st['new']
        if new is None: return
        buf.begin_user_action(); s_it, e_it = buf.get_iter_at_mark(sm), buf.get_iter_at_mark(em); buf.delete(s_it, e_it); s_it = buf.get_iter_at_mark(sm); buf.insert(s_it, new); buf.end_user_action()
        win.flash('изменение применено (Ctrl+Z отменит)'); d.response(Gtk.ResponseType.CLOSE)
    go.connect('clicked', run); ins.connect('activate', run); stop.connect('clicked', lambda _b: st['client'] and st['client'].cancel()); apply_b.connect('clicked', do_apply)
    d.show_all(); ins.grab_focus(); d.run()
    if st['client']: st['client'].cancel()
    d.destroy()


# ---------------------------------------------------------------- chat panel
class ChatPanel(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4); self.win = win; self.hist = []; self.busy = False; self.client = None; self.cur = None
        head = Gtk.Box(spacing=6); head.set_margin_start(6); head.set_margin_end(6); head.set_margin_top(4)
        self.title = Gtk.Label(label='', xalign=0); self.title.get_style_context().add_class('mono'); self.title.set_ellipsize(Pango.EllipsizeMode.END); head.pack_start(self.title, True, True, 0)
        for txt, cb in (('⚙', lambda: self.settings()), ('Очистить', lambda: self.clear())):
            b = Gtk.Button(label=txt); b.set_size_request(-1, 38); b.connect('clicked', lambda _b, f=cb: f()); head.pack_start(b, False, False, 0)
        self.pack_start(head, False, False, 0)
        h2 = Gtk.Box(spacing=6); h2.set_margin_start(6); h2.set_margin_end(6)
        self.c_file = Gtk.CheckButton(label='файл'); self.c_file.set_active(True); self.c_proj = Gtk.CheckButton(label='проект'); self.c_proj.set_active(True)
        self.c_file.set_tooltip_text('Добавлять текущий файл (или выделенное) к вопросу'); self.c_proj.set_tooltip_text('Добавлять список файлов проекта к вопросу')
        for w in (self.c_file, self.c_proj): h2.pack_start(w, False, False, 0)
        npb = Gtk.Button(label='Новый проект ИИ'); npb.set_size_request(-1, 38); npb.connect('clicked', lambda _b: new_project(win)); h2.pack_end(npb, False, False, 0); self.pack_start(h2, False, False, 0)
        q = Gtk.ScrolledWindow(); q.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER); qr = Gtk.Box(spacing=4); qr.set_margin_start(6); qr.set_margin_end(6); q.add(qr)
        for txt, prompt in QUICK:
            b = Gtk.Button(label=txt); b.set_size_request(-1, 38); b.connect('clicked', lambda _b, p=prompt: self.ask_about_code(p)); qr.pack_start(b, False, False, 0)
        b = Gtk.Button(label='Ошибка из терминала'); b.set_size_request(-1, 38); b.connect('clicked', lambda _b: self.ask_terminal()); qr.pack_start(b, False, False, 0)
        q.set_size_request(-1, 50); self.pack_start(q, False, False, 0)
        self.view = Gtk.TextView(); self.view.set_editable(False); self.view.set_cursor_visible(False); self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR); self.view.set_left_margin(10); self.view.set_right_margin(10)
        self.buf = self.view.get_buffer(); acc = '#39ff88' if ui.HACKER else '#ffffff'
        self.buf.create_tag('user', foreground=acc, weight=Pango.Weight.BOLD, pixels_above_lines=8); self.buf.create_tag('ai'); self.buf.create_tag('sys', foreground='#9a9a9a', style=Pango.Style.ITALIC)
        self.buf.create_tag('err', foreground='#ff8c8c'); self.buf.create_tag('code', family='Fira Code', size_points=10, paragraph_background='#0c0c0c' if not ui.HACKER else '#04120a', left_margin=18, right_margin=10)
        self.buf.create_tag('file', family='Fira Code', size_points=10, foreground=acc); sc = Gtk.ScrolledWindow(); sc.add(self.view); self.sc = sc; self.pack_start(sc, True, True, 0)
        inp = Gtk.Box(spacing=6); inp.set_margin_start(6); inp.set_margin_end(6); inp.set_margin_bottom(6)
        self.entry = entry('', 'спросите про код, ошибку или попросите создать файл…'); self.entry.connect('activate', lambda *_: self.send(self.entry.get_text()))
        self.send_b = Gtk.Button(label='Отправить'); self.send_b.connect('clicked', lambda _b: self.send(self.entry.get_text())); self.stop_b = Gtk.Button(label='Стоп'); self.stop_b.connect('clicked', lambda _b: self.stop())
        inp.pack_start(self.entry, True, True, 0); inp.pack_start(self.send_b, False, False, 0); inp.pack_start(self.stop_b, False, False, 0); self.pack_start(inp, False, False, 0)
        self.refresh_title(); self.sys_note('ИИ помогает с кодом и умеет создавать файлы и целые проекты. Ответы могут содержать ошибки: проверяйте их. Ничего не записывается и не запускается без вашего подтверждения.')
        self.show_all(); self.stop_b.hide()

    # ---- state
    def refresh_title(self):
        c = ai.load(); self.title.set_text('ИИ · ' + ai.describe(c))

    def settings(self):
        if open_settings(self.win): self.refresh_title()

    def clear(self):
        self.stop(); self.hist = []; self.buf.set_text(''); self.sys_note('Разговор очищен.')

    def stop(self):
        if self.client: self.client.cancel()

    # ---- transcript
    def end(self): return self.buf.get_end_iter()

    def put(self, text, tag): self.buf.insert_with_tags_by_name(self.end(), text, tag)

    def sys_note(self, text): self.put(text + '\n', 'sys'); self.scroll()

    def scroll(self): GLib.idle_add(lambda: (self.view.scroll_to_mark(self.buf.get_insert(), 0.0, False, 0, 0), False)[1]); self.buf.place_cursor(self.end())

    def code_buttons(self, lang, code):
        box = Gtk.Grid(row_spacing=4, column_spacing=4); box.set_column_homogeneous(True); n = [0]
        def btn(txt, fn):
            b = Gtk.Button(label=txt); b.set_can_focus(False); b.set_size_request(-1, 36); b.connect('clicked', lambda _b: fn()); box.attach(b, n[0] % 2, n[0] // 2, 1, 1); n[0] += 1
        btn('Вставить', lambda: self.insert_code(code, False)); btn('Заменить выделенное', lambda: self.insert_code(code, True)); btn('В новый файл', lambda: self.new_file(code, lang)); btn('Копировать', lambda: Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(code, -1))
        if lang.lower() in ('sh', 'bash', 'shell', 'console', 'zsh'): btn('Запустить в терминале…', lambda: self.run_code(code))
        box.show_all(); return box

    def anchor(self, widget):
        a = self.buf.create_child_anchor(self.end()); self.view.add_child_at_anchor(widget, a); self.put('\n', 'ai')

    def render(self, text):
        """styled version of an answer: code blocks with buttons, <file> blocks as one 'apply' row"""
        pos = 0; files = []
        spans = sorted([(m.start(), m.end(), 'file', m) for m in ai.FILE_TAG.finditer(text)] + [(m.start(), m.end(), 'code', m) for m in ai.FENCE.finditer(text)], key=lambda s: s[0])
        last_end = -1
        for s, e, kind, m in spans:
            if s < last_end: continue                                          # a fence inside a <file> block
            if s > pos: self.put(text[pos:s].strip('\n') + '\n', 'ai')
            if kind == 'code':
                lang, code = m.group(1), m.group(2); self.put(code + '\n', 'code'); self.anchor(self.code_buttons(lang, code))
            else:
                p = ai.parse_files(m.group(0))
                if p: files += p; self.put('📄 %s (%d строк)\n' % (p[0][0], p[0][1].count('\n') + 1), 'file')
            pos = last_end = e
        if pos < len(text): self.put(text[pos:].strip('\n') + '\n', 'ai')
        if files:
            b = Gtk.Button(label='Просмотреть и записать файлы (%d)…' % len(files)); b.set_can_focus(False); b.set_size_request(-1, 40); b.connect('clicked', lambda _b, f=files: apply_files(self.win, f)); b.show(); self.anchor(b)
        self.scroll()

    # ---- actions on the editor
    def insert_code(self, code, replace):
        doc = self.win.current()
        if doc is None: return
        b = doc.buf; b.begin_user_action()
        if replace and b.get_has_selection(): b.delete_selection(True, True)
        b.insert_at_cursor(code if code.endswith('\n') else code + '\n'); b.end_user_action(); self.win.flash('код вставлен (Ctrl+Z отменит)')

    def new_file(self, code, lang):
        self.win.new_doc(); doc = self.win.current(); doc.buf.set_text(code)
        try:
            from gi.repository import GtkSource
            l = GtkSource.LanguageManager.get_default().guess_language(None, 'text/x-' + lang.lower()) or GtkSource.LanguageManager.get_default().get_language(lang.lower())
            if l: doc.buf.set_language(l); doc.lang = l.get_name()
        except Exception: pass

    def run_code(self, code):
        lines = [l for l in code.strip().splitlines() if l.strip() and not l.strip().startswith('#')]
        bad = [l for l in lines if not ai.command_allowed(l)]
        if bad: self.win.msg('Эти команды заблокированы как небезопасные, ничего не запущено:\n' + '\n'.join(bad[:4])); return
        d = Gtk.MessageDialog(transient_for=self.win, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text='Выполнить в терминале?\n\n' + '\n'.join(lines[:12])); ui.style_app(d)
        r = d.run(); d.destroy()
        if r == Gtk.ResponseType.YES: self.win.term_run(' && '.join(lines))

    # ---- sending
    def context(self, with_sel_only=False):
        """text added to the question: project file list, selection or current file (never secret files)"""
        parts = []; w = self.win
        if self.c_proj.get_active() and os.path.isdir(w.folder):
            lst = ai.project_listing(w.folder)
            if lst: parts.append('Project folder files:\n' + '\n'.join('- ' + p for p in lst))
        doc = w.current()
        if doc is not None and (self.c_file.get_active() or with_sel_only) and not ai.SENSITIVE_NAMES.search(doc.path or ''):
            b = doc.buf; name = os.path.basename(doc.path or 'untitled')
            if b.get_has_selection():
                s, e = b.get_selection_bounds(); parts.append('Selected code in %s (lines %d-%d):\n```%s\n%s\n```' % (name, s.get_line() + 1, e.get_line() + 1, doc.lang.lower(), b.get_text(s, e, True)[:12000]))
            else:
                t = doc.text(); cut = len(t) > 12000
                parts.append('Current file %s (%s)%s:\n```%s\n%s\n```' % (name, doc.lang, ', truncated to the first 12000 characters' if cut else '', doc.lang.lower(), t[:12000]))
        return '\n\n'.join(parts)

    def ask_about_code(self, prompt):
        doc = self.win.current()
        if doc is None or not (doc.buf.get_has_selection() or doc.text().strip()): self.sys_note('Откройте файл (или выделите код), к которому относится вопрос.'); return
        self.send(prompt, force_ctx=True)

    def ask_terminal(self):
        t = self.win.term
        txt = ai.mask_secrets(rt.recent_text(t, 60)) if t is not None else ''
        if not txt.strip(): self.sys_note('В терминале пока нет вывода. Запустите программу (F5), получите ошибку и нажмите снова.'); return
        self.send('Вот последний вывод терминала. Объясни ошибку и предложи исправление; если нужно изменить файл, покажи изменение.\n\nВывод терминала:\n```\n%s\n```' % txt, force_ctx=True)

    def send(self, text, force_ctx=False):
        text = (text or '').strip()
        if not text or self.busy: return
        cfg = ai.load()
        if not ai.configured(cfg):
            self.sys_note('ИИ не настроен. Откройте настройки и введите ключ или адрес локального сервера.')
            if open_settings(self.win): self.refresh_title(); cfg = ai.load()
            if not ai.configured(cfg): return
        if not confirm_host(self.win, cfg): return
        ctx = self.context(force_ctx)
        full = (ctx + '\n\nQuestion:\n' + text) if ctx else text
        rules = ''
        try: rules = open(os.path.join(self.win.folder, '.rembly-ai.md'), errors='replace').read()
        except OSError: pass
        msgs = ai.trim_history(self.hist) + [{'role': 'user', 'content': full}]
        shown = text if len(text) < 600 else text[:600] + '…'
        self.put('Вы: ' + shown + '\n', 'user'); self.put('ИИ: ', 'user'); self.cur = self.buf.create_mark(None, self.end(), True)
        self.entry.set_text(''); self.busy = True; self.send_b.hide(); self.stop_b.show(); self.client = cl = ai.Client(cfg); self.scroll()

        def work():
            return cl.chat(msgs, system=ai.system_chat(rules), on_text=lambda p: GLib.idle_add(self.on_chunk, p))
        run_thread(work, lambda r, e: self.on_done(text, r, e))

    def on_chunk(self, piece):
        self.put(piece, 'ai'); self.scroll(); return False

    def on_done(self, question, out, err):
        self.busy = False; self.send_b.show(); self.stop_b.hide()
        start = self.buf.get_iter_at_mark(self.cur); self.buf.delete(start, self.end()); self.buf.delete_mark(self.cur); self.cur = None
        if err: self.put('✖ ' + err + '\n', 'err'); self.scroll(); return
        if not (out or '').strip(): self.put('(пустой ответ)\n', 'sys'); return
        self.render(out); self.hist += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': out}]; self.hist = ai.trim_history(self.hist, 40000, 20)


# ---------------------------------------------------------------- project wizard
class ProjectWizard(Gtk.Dialog):
    """describe -> AI plans (files, commands) -> you review -> AI writes every file -> project folder opens. Files are written into a NEW folder only."""
    def __init__(self, win):
        super().__init__(title='ИИ создаёт проект', transient_for=win, modal=True); ui.style_app(self); self.win = win; self.client = None; self.plan = None; self.root = None; self.stop_flag = False; self.written = []
        self.set_default_size(min(900, ui.screen_size()[0] - 20), min(660, ui.screen_size()[1] - 100)); self.cfg = ai.load()
        self.stack = Gtk.Stack(); self.get_content_area().pack_start(self.stack, True, True, 0); self.get_content_area().set_border_width(10)
        for name, page in (('ask', self.page_ask()), ('plan', self.page_plan()), ('run', self.page_run()), ('done', self.page_done())):
            sc = Gtk.ScrolledWindow(); sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); sc.add(page); self.stack.add_named(sc, name)          # small screens: a page scrolls instead of making the dialog taller than the screen
        self.stack.set_vhomogeneous(False); self.stack.set_hhomogeneous(False)
        self.btn_close = self.add_button('Закрыть', Gtk.ResponseType.CLOSE); self.show_all(); self.stack.set_visible_child_name('ask')

    # -- pages
    def page_ask(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        b.pack_start(Gtk.Label(label='Опишите проект своими словами: что он делает, на чём написан, для чего. ИИ составит план, вы его проверите, потом он напишет файлы.', xalign=0, wrap=True), False, False, 0)
        self.desc = Gtk.TextView(); self.desc.set_wrap_mode(Gtk.WrapMode.WORD_CHAR); self.desc.set_left_margin(8); self.desc.set_top_margin(6); sc = Gtk.ScrolledWindow(); sc.add(self.desc); sc.set_size_request(-1, 110); b.pack_start(sc, True, True, 0)
        self.desc.connect('focus-in-event', lambda *_: ui.osk(True))
        fl = Gtk.FlowBox(); fl.set_selection_mode(Gtk.SelectionMode.NONE); fl.set_max_children_per_line(2); fl.set_homogeneous(False)
        for ex in EXAMPLES:
            x = Gtk.Button(label=ex); x.get_child().set_line_wrap(True); x.get_child().set_max_width_chars(34); x.connect('clicked', lambda _b, t=ex: self.desc.get_buffer().set_text(t)); fl.add(x)
        b.pack_start(Gtk.Label(label='Примеры (нажмите, чтобы подставить):', xalign=0), False, False, 0); b.pack_start(fl, False, False, 0)
        g = Gtk.Grid(row_spacing=6, column_spacing=10); self.stack_c = Gtk.ComboBoxText(); [self.stack_c.append(k, t) for k, t in STACKS]; self.stack_c.set_active_id('auto')
        self.name_e = entry('', 'пусто — ИИ придумает имя'); self.dir_e = entry(os.path.expanduser('~/Projects')); self.git_c = Gtk.CheckButton(label='создать git-репозиторий'); self.git_c.set_active(bool(ui.have('git')))
        self.open_c = Gtk.CheckButton(label='открыть проект в редакторе'); self.open_c.set_active(True)
        for i, (lab, w) in enumerate((('Язык / стек', self.stack_c), ('Имя папки', self.name_e), ('Где создать', self.dir_e))):
            g.attach(Gtk.Label(label=lab, xalign=0), 0, i, 1, 1); g.attach(w, 1, i, 1, 1)
        g.attach(self.git_c, 1, 3, 1, 1); g.attach(self.open_c, 1, 4, 1, 1); b.pack_start(g, False, False, 0)
        self.ask_msg = Gtk.Label(label='', xalign=0, wrap=True); b.pack_start(self.ask_msg, False, False, 0)
        row = Gtk.Box(spacing=8); self.plan_b = Gtk.Button(label='Составить план'); self.plan_b.connect('clicked', lambda _b: self.make_plan()); sb = Gtk.Button(label='⚙ Настройки ИИ'); sb.connect('clicked', lambda _b: (open_settings(self.win), setattr(self, 'cfg', ai.load())))
        row.pack_start(self.plan_b, False, False, 0); row.pack_start(sb, False, False, 0); b.pack_start(row, False, False, 0); return b

    def page_plan(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.p_summary = Gtk.Label(label='', xalign=0, wrap=True); b.pack_start(self.p_summary, False, False, 0)
        nr = Gtk.Box(spacing=8); nr.pack_start(Gtk.Label(label='Папка проекта:'), False, False, 0); self.p_name = entry(); nr.pack_start(self.p_name, True, True, 0); b.pack_start(nr, False, False, 0)
        self.fstore = Gtk.ListStore(bool, str, str); tv = Gtk.TreeView(model=self.fstore); tv.set_headers_visible(False)
        r = Gtk.CellRendererToggle(); r.connect('toggled', lambda w, p: self.fstore.__setitem__(p, [not self.fstore[p][0], self.fstore[p][1], self.fstore[p][2]])); tv.append_column(Gtk.TreeViewColumn('', r, active=0))
        t = Gtk.CellRendererText(); t.set_property('ypad', 6); tv.append_column(Gtk.TreeViewColumn('', t, text=1)); t2 = Gtk.CellRendererText(); t2.set_property('foreground', '#bdbdbd'); t2.set_property('ellipsize', Pango.EllipsizeMode.END)
        c2 = Gtk.TreeViewColumn('', t2, text=2); c2.set_expand(True); tv.append_column(c2); sc = Gtk.ScrolledWindow(); sc.add(tv); b.pack_start(sc, True, True, 0)
        self.p_cmds = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); b.pack_start(self.p_cmds, False, False, 0)
        self.p_warn = Gtk.Label(label='', xalign=0, wrap=True); b.pack_start(self.p_warn, False, False, 0)
        row = Gtk.Box(spacing=8); back = Gtk.Button(label='Назад'); back.connect('clicked', lambda _b: self.stack.set_visible_child_name('ask')); self.create_b = Gtk.Button(label='Создать проект'); self.create_b.connect('clicked', lambda _b: self.create())
        row.pack_start(back, False, False, 0); row.pack_start(self.create_b, False, False, 0); b.pack_start(row, False, False, 0); return b

    def page_run(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); self.r_label = Gtk.Label(label='', xalign=0, wrap=True); self.r_bar = Gtk.ProgressBar(); b.pack_start(self.r_label, False, False, 0); b.pack_start(self.r_bar, False, False, 0)
        self.live = Gtk.TextView(); self.live.set_editable(False); self.live.get_style_context().add_class('mono'); self.live.set_wrap_mode(Gtk.WrapMode.CHAR); sc = Gtk.ScrolledWindow(); sc.add(self.live); b.pack_start(sc, True, True, 0)
        self.r_stop = Gtk.Button(label='Остановить'); self.r_stop.connect('clicked', lambda _b: self.stop()); b.pack_start(self.r_stop, False, False, 0); return b

    def page_done(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); self.d_label = Gtk.Label(label='', xalign=0, wrap=True); b.pack_start(self.d_label, False, False, 0)
        self.d_cmds = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); b.pack_start(self.d_cmds, False, False, 0)
        row = Gtk.Box(spacing=8); self.open_b = Gtk.Button(label='Открыть проект'); self.open_b.connect('clicked', lambda _b: self.finish(False)); self.run_b = Gtk.Button(label='Выполнить отмеченные команды в терминале'); self.run_b.connect('clicked', lambda _b: self.finish(True))
        row.pack_start(self.open_b, False, False, 0); row.pack_start(self.run_b, False, False, 0); b.pack_start(row, False, False, 0); return b

    # -- step 1: plan
    def stack_hint(self):
        k = self.stack_c.get_active_id()
        return {'auto': '', 'python': 'Use Python 3.8.', 'node': 'Use JavaScript for Node.js 10 (no modern syntax like optional chaining).', 'web': 'Use plain HTML, CSS and JavaScript, no build step.', 'c': 'Use C (gcc 9) with a Makefile or CMake.',
                'cpp': 'Use C++ (g++ 9) with CMake.', 'go': 'Use Go.', 'bash': 'Use Bash.'}[k]

    def description(self):
        b = self.desc.get_buffer(); return b.get_text(b.get_start_iter(), b.get_end_iter(), True).strip()

    def make_plan(self):
        text = self.description()
        if len(text) < 8: self.ask_msg.set_text('Опишите проект подробнее (хотя бы одно предложение).'); return
        self.cfg = ai.load()
        if not ai.configured(self.cfg):
            if not open_settings(self.win): return
            self.cfg = ai.load()
            if not ai.configured(self.cfg): return
        if not confirm_host(self.win, self.cfg): return
        self.plan_b.set_sensitive(False); self.ask_msg.set_text('ИИ составляет план проекта…'); cl = self.client = ai.Client(self.cfg)
        user = 'Project request: %s\n%s' % (text, self.stack_hint())
        def done(r, e):
            self.plan_b.set_sensitive(True)
            if e: self.ask_msg.set_text('✖ ' + e); return
            try: self.plan = ai.parse_plan(r)
            except ai.AIError as ex:
                self.ask_msg.set_text('✖ %s' % ex); return
            self.show_plan(text)
        run_thread(lambda: cl.chat([{'role': 'user', 'content': user}], system=ai.SYSTEM_PLAN, max_tokens=max(int(self.cfg.get('max_tokens', 2048)), 3000)), done)

    def show_plan(self, text):
        p = self.plan; self.p_summary.set_text('План: %s' % (p['summary'] or p['name'])); self.p_name.set_text(self.name_e.get_text().strip() or p['name']); self.fstore.clear()
        ok, bad = ai.check_files([(f['path'], '') for f in p['files']]); purpose = {f['path']: f['purpose'] for f in p['files']}; self.plan_ok = [(rel, purpose.get(rel) or purpose.get(rel.replace('/', os.sep), '')) for rel, _c, _e in ok]
        for rel, why in self.plan_ok: self.fstore.append([True, rel, why])
        self.p_warn.set_text(('Пропущено ИИ-путей (небезопасно): ' + '; '.join('%s — %s' % (a, w) for a, w in bad)) if bad else '')
        for ch in self.p_cmds.get_children(): self.p_cmds.remove(ch)
        self.cmd_checks = []
        cmds = [('Установка: ' + c, c) for c in p['setup']] + ([('Запуск: ' + p['run'], p['run'])] if p['run'] else [])
        if cmds: self.p_cmds.pack_start(Gtk.Label(label='Команды, которые предложил ИИ (после создания; выполняются только отмеченные и только в терминале у вас на глазах):', xalign=0, wrap=True), False, False, 0)
        for label, c in cmds:
            cb = Gtk.CheckButton(label=label if ai.command_allowed(c) else label + '   — ЗАБЛОКИРОВАНО (небезопасно)'); cb.set_sensitive(ai.command_allowed(c)); cb.set_active(False); self.p_cmds.pack_start(cb, False, False, 0); self.cmd_checks.append((c, cb))
        self.p_cmds.show_all(); self.stack.set_visible_child_name('plan')

    # -- step 2: write files
    def create(self):
        sel = {row[1] for row in self.fstore if row[0]}; files = [(rel, why) for rel, why in self.plan_ok if rel in sel]
        if not files: self.p_warn.set_text('Отметьте хотя бы один файл.'); return
        base = os.path.expanduser(self.dir_e.get_text().strip() or '~/Projects'); name = ai.sanitize_name(self.p_name.get_text())
        try: os.makedirs(base, exist_ok=True)
        except OSError as e: self.p_warn.set_text('Не удалось создать %s: %s' % (base, e)); return
        self.root = ai.unique_dir(base, name); self.picked_cmds = [c for c, cb in self.cmd_checks if cb.get_active()]
        try: os.makedirs(self.root)
        except OSError as e: self.p_warn.set_text('Не удалось создать папку: %s' % e); return
        self.stack.set_visible_child_name('run'); self.stop_flag = False; self.written = []; self.failed = []; self.btn_close.set_sensitive(False)
        self.live.get_buffer().set_text(''); self.r_bar.set_fraction(0); self.cl = self.client = ai.Client(self.cfg); text = self.description(); plan = self.plan
        threading.Thread(target=self.gen_worker, args=(files, text, plan), daemon=True).start()

    def stop(self):
        self.stop_flag = True
        if self.client: self.client.cancel()

    def ui(self, fn, *a): GLib.idle_add(lambda: (fn(*a), False)[1])

    def gen_worker(self, files, text, plan):
        done_ctx = []; n = len(files); mt = max(int(self.cfg.get('max_tokens', 2048)), 4000)
        plan_txt = '\n'.join('- %s: %s' % (r, w) for r, w in files)
        for i, (rel, why) in enumerate(files):
            if self.stop_flag: break
            self.ui(self.r_label.set_text, 'Файл %d из %d: %s' % (i + 1, n, rel)); self.ui(self.r_bar.set_fraction, i / float(n)); self.ui(self.live.get_buffer().set_text, '')
            ctx = ''; budget = 6000
            for pr, pc in reversed(done_ctx):
                chunk = '=== %s ===\n%s\n' % (pr, pc[:1500])
                if len(ctx) + len(chunk) > budget: break
                ctx = chunk + ctx
            user = 'Project: %s\nUser request: %s\n%s\nPlan (all files):\n%s\n\nFiles already written:\n%s\nTARGET FILE: %s\nPurpose: %s' % (plan['summary'], text, self.stack_hint(), plan_txt, ctx or '(none yet)', rel, why)
            buf = []
            def prog(p):
                buf.append(p); self.ui(self.show_live, ''.join(buf)[-1500:])
            try: out = self.client.chat([{'role': 'user', 'content': user}], system=ai.SYSTEM_FILE, max_tokens=mt, on_text=prog)
            except ai.AIError as e:
                self.failed.append((rel, str(e)));
                if self.stop_flag: break
                if 'HTTP 4' in str(e) or 'нет связи' in str(e): break                                  # the server refuses or is gone: do not hammer it for every file
                continue
            if self.stop_flag: break
            code = ai.first_code(out or '')
            ok, bad = ai.check_files([(rel, code)])
            if not ok or not code.strip(): self.failed.append((rel, 'пустой или недопустимый ответ')); continue
            w = ai.write_files(self.root, [(rel, code)])
            if w: self.written += w; done_ctx.append((rel, code))
        self.ui(self.gen_done, bool(self.stop_flag))

    def show_live(self, t):
        self.live.get_buffer().set_text(t); return False

    def gen_done(self, stopped):
        self.btn_close.set_sensitive(True); self.r_bar.set_fraction(1.0)
        if self.git_c.get_active() and self.written:
            try: subprocess.run(['git', 'init', '-q'], cwd=self.root, capture_output=True, timeout=20)
            except Exception: pass
        txt = 'Готово: %s\nСоздано файлов: %d\n  %s' % (self.root, len(self.written), '\n  '.join(self.written[:30]))
        if stopped: txt += '\nОстановлено вами: проект создан частично.'
        if self.failed: txt += '\nНе удалось (%d): ' % len(self.failed) + '; '.join('%s — %s' % (r, w[:80]) for r, w in self.failed[:5])
        self.d_label.set_text(txt)
        for ch in self.d_cmds.get_children(): self.d_cmds.remove(ch)
        self.done_checks = []
        for c in getattr(self, 'picked_cmds', []):
            cb = Gtk.CheckButton(label=c); cb.set_active(True); self.d_cmds.pack_start(cb, False, False, 0); self.done_checks.append((c, cb))
        self.d_cmds.show_all(); self.run_b.set_visible(bool(self.done_checks)); self.stack.set_visible_child_name('done')
        if not self.written: self.open_b.set_label('Закрыть')

    def finish(self, run_cmds):
        cmds = [c for c, cb in getattr(self, 'done_checks', []) if cb.get_active() and ai.command_allowed(c)] if run_cmds else []
        root = self.root; first = next((p for p in ('README.md', 'main.py', 'app.py', 'index.html') if p in self.written), self.written[0] if self.written else None)
        self.response(Gtk.ResponseType.CLOSE)
        if root and self.written and self.open_c.get_active():
            self.win.set_folder(root)
            if first: self.win.open_file(os.path.join(root, first))
        if cmds: self.win.term_run('cd "%s" && %s' % (root, ' && '.join(cmds)))


def new_project(win):
    d = ProjectWizard(win); d.run(); d.stop(); d.destroy()
