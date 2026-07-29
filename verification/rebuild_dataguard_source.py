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
    if old not in text:
        raise SystemExit("distribution selection pattern missing")
    app.write_text(text.replace(old, new, 1), encoding="utf-8")

    user = root / "DataGuardUser.py"
    text = user.read_text(encoding="utf-8")
    text = text.replace(
        '            destination.parent.mkdir(parents=True, exist_ok=True)\n            shutil.move(selected, destination)',
        '            destination.parent.mkdir(parents=True, exist_ok=True)\n            shutil.move(selected, destination)\n            qc_status = "待质检" if destination_name == USER_DONE else "返修提交"\n            qc_root = Path(self.project_var.get()) / "04_Quality_Check" / "质检工作台" / qc_status / self.user_var.get() / relative\n            if qc_root.exists():\n                raise FileExistsError(f"质检目录中已存在：{qc_root}")\n            qc_root.parent.mkdir(parents=True, exist_ok=True)\n            shutil.copytree(destination, qc_root)',
        1,
    )
    user.write_text(text, encoding="utf-8")

    constants = root / "alchemy" / "constants.py"
    ctext = constants.read_text(encoding="utf-8").replace("v1.9.20", "v1.9.21")
    constants.write_text(ctext, encoding="utf-8")
    for p in root.rglob("*.txt"):
        try:
            p.write_text(p.read_text(encoding="utf-8", errors="ignore").replace("v1.9.20", "v1.9.21"), encoding="utf-8")
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
