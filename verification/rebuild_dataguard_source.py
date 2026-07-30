from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import shutil
import tempfile

archive = Path("dataguard/dataguard-source.zip")
root = Path(tempfile.mkdtemp())
try:
    with ZipFile(archive) as z:
        z.extractall(root)

    app = root / "alchemy" / "app.py"
    text = app.read_text(encoding="utf-8")
    backend = root / "alchemy" / "backend.py"
    backend_text = backend.read_text(encoding="utf-8")
    marker = "    def get_raw_categories(self):"
    methods = '''    def create_raw_category(self, name):
        name = str(name or "").strip()
        if not name or name in {".", ".."} or any(ch in name for ch in '<>:"/\\\\|?*'):
            return False, "类别名称无效"
        path = os.path.join(self.dirs["RAW"], name)
        if os.path.exists(path): return False, f"类别 [{name}] 已存在"
        try: os.makedirs(path, exist_ok=False); return True, f"类别 [{name}] 创建成功"
        except OSError as exc: return False, f"创建类别失败: {exc}"

    def create_raw_batch(self, category, name):
        category, name = str(category or "").strip(), str(name or "").strip()
        if not category or not name or name in {".", ".."} or any(ch in name for ch in '<>:"/\\\\|?*'):
            return False, "批次名称无效"
        parent = os.path.join(self.dirs["RAW"], category)
        if not os.path.isdir(parent): return False, "请先创建类别"
        path = os.path.join(parent, name)
        if os.path.exists(path): return False, f"批次 [{name}] 已存在"
        try: os.makedirs(path, exist_ok=False); return True, f"批次 [{name}] 创建成功"
        except OSError as exc: return False, f"创建批次失败: {exc}"

    def import_raw_images(self, category, batch, paths):
        target = os.path.join(self.dirs["RAW"], str(category or ""), str(batch or ""))
        if not os.path.isdir(target): return False, "请先创建类别和批次"
        copied = 0
        for source in paths or ():
            if os.path.isfile(source) and os.path.splitext(source)[1].lower() in IMAGE_EXTENSIONS:
                destination = os.path.join(target, os.path.basename(source))
                if not os.path.exists(destination): shutil.copy2(source, destination); copied += 1
        return True, f"已导入 {copied} 张图片"

    def _harvest_workbench(self, user, status_name, target_root, today_str, separate_psd, msg_queue, cancel_flag):
        """回收统一质检工作台中的已提交任务，避免用户端提交后管理端扫描不到。"""
        source_root = os.path.join(self.dirs["QC"], "质检工作台", status_name, user)
        if not os.path.isdir(source_root):
            return 0, 0
        moved = skipped = 0
        for recovery_path, folder_name, src in list(self._iter_classified_tasks(source_root)):
            if cancel_flag and cancel_flag():
                break
            dst = os.path.join(target_root, *recovery_path, user, folder_name)
            ok, msg = self._safe_move(src, dst, msg_queue=msg_queue)
            if ok:
                moved += 1
                if separate_psd:
                    self._separate_psd_files(dst, user, folder_name, msg_queue=msg_queue)
            else:
                skipped += 1
                self.log(f"质检工作台回收失败 {folder_name}: {msg}")
        return moved, skipped

'''
    if marker in backend_text:
        if "def create_raw_category" not in backend_text:
            backend_text = backend_text.replace(marker, methods + marker, 1)
        elif "def _harvest_workbench" not in backend_text:
            workbench = methods[methods.index("    def _harvest_workbench"):]
            backend_text = backend_text.replace(marker, workbench + marker, 1)
        backend.write_text(backend_text, encoding="utf-8")
    text = text.replace(
        '        ttk.Label(frame_cat, text="类别:", width=6).pack(side="left", anchor="n", pady=5)',
        '        ttk.Label(frame_cat, text="类别:", width=6).pack(side="left", anchor="n", pady=5)\n        ttk.Button(frame_cat, text="+ 创建类别", bootstyle="success-outline", command=self.on_create_category).pack(side="right", padx=2)', 1)
    text = text.replace(
        '        ttk.Label(frame_batch, text="批次:", width=6).pack(side="left")',
        '        ttk.Label(frame_batch, text="批次:", width=6).pack(side="left")\n        ttk.Button(frame_batch, text="+ 创建批次", bootstyle="success-outline", command=self.on_create_batch).pack(side="right", padx=2)', 1)
    text = text.replace(
        '        frame_group = ttk.Frame(frame_left)\n        frame_group.pack(fill="x", pady=(10, 2))',
        '        ttk.Button(frame_left, text="导入图片到当前批次", bootstyle="info-outline", command=self.on_import_images).pack(fill="x", pady=(6, 2))\n        frame_group = ttk.Frame(frame_left)\n        frame_group.pack(fill="x", pady=(10, 2))', 1)
    handlers = '''    def on_create_category(self):
        name = simpledialog.askstring("创建类别", "类别名称：", parent=self.root)
        if name:
            ok, msg = self.backend.create_raw_category(name)
            (messagebox.showinfo if ok else messagebox.showerror)("类别", msg, parent=self.root)
            if ok: self.refresh_categories_and_batches()

    def on_create_batch(self):
        category = self.var_category.get()
        if not category: return messagebox.showwarning("批次", "请先选择类别", parent=self.root)
        name = simpledialog.askstring("创建批次", f"类别 [{category}] 的批次名称：", parent=self.root)
        if name:
            ok, msg = self.backend.create_raw_batch(category, name)
            (messagebox.showinfo if ok else messagebox.showerror)("批次", msg, parent=self.root)
            if ok: self.refresh_categories_and_batches()

    def on_import_images(self):
        category, batch = self.var_category.get(), self.combo_batches.get()
        if not category or not batch: return messagebox.showwarning("导入图片", "请先选择类别和批次", parent=self.root)
        paths = filedialog.askopenfilenames(title="选择要导入的图片", filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"), ("全部文件", "*.*")])
        if paths:
            ok, msg = self.backend.import_raw_images(category, batch, paths)
            (messagebox.showinfo if ok else messagebox.showerror)("导入图片", msg, parent=self.root)
            if ok: self.on_category_btn_click()

'''
    if "def on_create_category" not in text:
        text = text.replace("    def on_create_user_click(self):", handlers + "    def on_create_user_click(self):", 1)
    text = text.replace(
        '        if success:\n            self.append_log(msg)\n            messagebox.showinfo("完成", msg)',
        '        if success:\n            self.refresh_categories_and_batches()\n            self.refresh_users()\n            self.refresh_harvest_status()\n            self.refresh_dates()\n            self.refresh_qa_targets()\n            self.append_log(msg)\n            messagebox.showinfo("完成", msg)',
        1,
    )
    text = text.replace(
        '        cat = self.var_category.get()\n        batch = self.combo_batches.get()\n        if not cat or not batch:\n            return messagebox.showwarning("提示", "请先选择类别和批次")\n        # 弹窗：输入分组名 + 选择类型',
        '        cat = self.var_category.get()\n        batch = self.combo_batches.get()\n        if not cat:\n            self.refresh_categories_and_batches()\n            cat = self.var_category.get()\n        if not batch and self.combo_batches["values"]:\n            self.combo_batches.current(0)\n            batch = self.combo_batches.get()\n            self.on_batch_selected(None)\n        if not cat or not batch:\n            return messagebox.showwarning("提示", "请先在左侧选择一个类别和批次；没有批次时请先把图片放入 01_Raw_Data/类别/批次。")\n        # 弹窗：输入分组名 + 选择类型',
        1,
    )
    old = '''        cat = self.var_category.get()
        batch = self.combo_batches.get()
        raw_indices = self.list_raw.curselection()
        user_indices = self.list_users_dist.curselection()
        user_list = [self.list_users_dist.get(i) for i in user_indices]
        recovery_path = tuple(p for p in (self.var_recovery_level1.get(), self.var_recovery_level2.get()) if p)
        if not cat or not batch or not raw_indices or not user_list:
            return messagebox.showwarning("提示", "请完整选择！")'''
    new = '''        cat = self.var_category.get()
        batch = self.combo_batches.get()
        if not cat:
            self.refresh_categories_and_batches()
            cat = self.var_category.get()
        if not batch and self.combo_batches["values"]:
            self.combo_batches.current(0)
            batch = self.combo_batches.get()
            self.on_batch_selected(None)
        if not self.list_raw.curselection() and self.list_raw.size():
            self.select_all()
        if not self.list_users_dist.curselection() and self.list_users_dist.size():
            self.list_users_dist.select_set(0, tk.END)
        raw_indices = self.list_raw.curselection()
        user_indices = self.list_users_dist.curselection()
        user_list = [self.list_users_dist.get(i) for i in user_indices]
        recovery_path = tuple(p for p in (self.var_recovery_level1.get(), self.var_recovery_level2.get()) if p)
        missing = []
        if not cat: missing.append("类别")
        if not batch: missing.append("批次")
        if not raw_indices: missing.append("图片/任务")
        if not user_list: missing.append("目标人员")
        if missing:
            return messagebox.showwarning("还差一步", "请先准备：" + "、".join(missing) + "。类别/批次在左侧，图片在中间，人员在右侧。")'''
    if old in text:
        text = text.replace(old, new, 1)
    harvest_marker = '            n, a, s = self._harvest_done(user, qc_new_root, qc_abandoned_dir, today_str, separate_psd, msg_queue, cancel_flag)'
    harvest_insert = '''            wb_new, wb_new_skipped = self._harvest_workbench(user, "待质检", qc_new_root, today_str, separate_psd, msg_queue, cancel_flag)
            wb_rework, wb_rework_skipped = self._harvest_workbench(user, "返修提交", qc_rework_root, today_str, separate_psd, msg_queue, cancel_flag)
            cnt_new += wb_new; cnt_rework += wb_rework; cnt_skipped += wb_new_skipped + wb_rework_skipped
'''
    if harvest_marker in backend_text and "_harvest_workbench(user" not in backend_text:
        backend_text = backend_text.replace(harvest_marker, harvest_insert + harvest_marker, 1)
        backend.write_text(backend_text, encoding="utf-8")
    app.write_text(text, encoding="utf-8")

    user = root / "DataGuardUser.py"
    text = user.read_text(encoding="utf-8")
    text = text.replace(
        '            destination.parent.mkdir(parents=True, exist_ok=True)\n            shutil.move(selected, destination)\n            qc_status = "待质检" if destination_name == USER_DONE else "返修提交"\n            qc_root = Path(self.project_var.get()) / "04_Quality_Check" / "质检工作台" / qc_status / self.user_var.get() / relative\n            if qc_root.exists():\n                raise FileExistsError(f"质检目录中已存在：{qc_root}")\n            qc_root.parent.mkdir(parents=True, exist_ok=True)\n            shutil.copytree(destination, qc_root)',
        '            qc_status = "待质检" if destination_name == USER_DONE else "返修提交"\n            qc_root = Path(self.project_var.get()) / "04_Quality_Check" / "质检工作台" / qc_status / self.user_var.get() / relative\n            if qc_root.exists():\n                raise FileExistsError(f"质检目录中已存在：{qc_root}")\n            qc_root.parent.mkdir(parents=True, exist_ok=True)\n            shutil.move(selected, qc_root)',
        1,
    )
    text = text.replace(
        '            destination.parent.mkdir(parents=True, exist_ok=True)\n            shutil.move(selected, destination)',
        '            destination.parent.mkdir(parents=True, exist_ok=True)\n            shutil.move(selected, destination)\n            qc_status = "待质检" if destination_name == USER_DONE else "返修提交"\n            qc_root = Path(self.project_var.get()) / "04_Quality_Check" / "质检工作台" / qc_status / self.user_var.get() / relative\n            if qc_root.exists():\n                raise FileExistsError(f"质检目录中已存在：{qc_root}")\n            qc_root.parent.mkdir(parents=True, exist_ok=True)\n            shutil.copytree(destination, qc_root)',
        1,
    )
    user.write_text(text, encoding="utf-8")

    regression = root / "tests" / "test_workbench_harvest.py"
    regression.write_text('''import datetime\nimport os\nimport tempfile\nimport unittest\n\nfrom alchemy.backend import AlchemyBackend\nfrom alchemy.constants import DATE_FMT, QC_NEW\n\n\nclass WorkbenchHarvestTests(unittest.TestCase):\n    def test_user_submission_workbench_is_recovered(self):\n        with tempfile.TemporaryDirectory() as root:\n            backend = AlchemyBackend()\n            backend.set_root(root)\n            backend.init_directories()\n            backend.create_user_folders("U")\n            source = os.path.join(backend.dirs["QC"], "质检工作台", "待质检", "U", "12345678")\n            os.makedirs(source)\n            result = backend.harvest(target_user="U", collect_unfinished=False)\n            today = datetime.datetime.now().strftime(DATE_FMT)\n            target = os.path.join(backend.dirs["QC"], QC_NEW, today, "U", "12345678")\n            self.assertEqual(result[0], 1)\n            self.assertTrue(os.path.isdir(target))\n            self.assertFalse(os.path.exists(source))\n            backend.close()\n\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding="utf-8")

    constants = root / "alchemy" / "constants.py"
    ctext = constants.read_text(encoding="utf-8").replace("v1.9.20", "v1.9.22").replace("v1.9.21", "v1.9.22")
    constants.write_text(ctext, encoding="utf-8")
    for p in root.rglob("*.txt"):
        try:
            p.write_text(p.read_text(encoding="utf-8", errors="ignore").replace("v1.9.20", "v1.9.22").replace("v1.9.21", "v1.9.22"), encoding="utf-8")
        except OSError:
            pass

    rebuilt = archive.with_suffix(".rebuilt.zip")
    with ZipFile(rebuilt, "w", ZIP_DEFLATED) as z:
        for p in root.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(root).as_posix())
    shutil.copy2(rebuilt, archive)
finally:
    shutil.rmtree(root, ignore_errors=True)
