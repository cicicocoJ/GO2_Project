
---

# 📘 GO2_Project 后期开发与Git更新操作手册

## 📌 一、项目位置

```bash
~/GO2_Project
```

进入项目：

```bash
cd ~/GO2_Project
```

---

# 🚀 二、日常开发流程（最重要）

以后每次改代码后，只需要执行以下三步：

## 1️⃣ 查看改动

```bash
git status
```

---

## 2️⃣ 添加修改文件

```bash
git add .
```

---

## 3️⃣ 提交版本

```bash
git commit -m "本次修改说明"
```

示例：

```bash
git commit -m "修复ROS2通信问题"
git commit -m "优化巡检任务逻辑"
git commit -m "更新bridge接口"
```

---

## 4️⃣ 推送到GitHub

```bash
git push
```

---

# ⚠️ 三、如果你用的是 SSH（推荐）

确保远程是 SSH：

```bash
git remote -v
```

应该是：

```bash
git@github.com:cicicocoJ/GO2_Project.git
```

---

如果不是，改成 SSH：

```bash
git remote set-url origin git@github.com:cicicocoJ/GO2_Project.git
```

---

# 🔥 四、首次配置（只做一次）

## 1. 配置用户名

```bash
git config --global user.name "cicicocoJ"
git config --global user.email "你的GitHub邮箱"
```

---

## 2. 配置 SSH（推荐长期使用）

生成密钥：

```bash
ssh-keygen -t ed25519 -C "你的GitHub邮箱"
```

查看公钥：

```bash
cat ~/.ssh/id_ed25519.pub
```

复制到：

👉 GitHub → Settings → SSH Keys

测试：

```bash
ssh -T git@github.com
```

---

# 🧱 五、项目结构更新规范（建议）

以后开发尽量遵守：

```text
GO2_Project/
├── go2_bridge_ws/        # ROS2 bridge
├── backend/              # 后端服务
├── control/              # 控制逻辑
├── perception/           # 感知模块
├── scripts/              # 工具脚本
├── docs/                 # 文档
├── .gitignore
└── README.md
```

---

# 🚫 六、必须忽略的文件（不要上传Git）

确保 `.gitignore` 包含：

```gitignore
build/
install/
log/
__pycache__/
*.pyc
*.bag
*.db3
.vscode/
CMakeFiles/
CMakeCache.txt
```

---

# ⚡ 七、常见问题处理

---

## ❌ 1. push 卡住 / timeout

解决：

```bash
git push
```

如果仍失败，改 SSH：

```bash
git remote set-url origin git@github.com:cicicocoJ/GO2_Project.git
```

---

## ❌ 2. add时报错（子仓库问题）

如果提示：

```text
not a valid object name
```

执行：

```bash
find . -name .git -type d -exec rm -rf {} +
```

然后：

```bash
git add .
```

---

## ❌ 3. 忘记提交顺序

标准流程：

```bash
git status
git add .
git commit -m "xxx"
git push
```

---

# 📦 八、推荐开发节奏（非常重要）

建议你每次：

### ✔ 小改动

* 1次 commit

### ✔ 一个功能完成

* 1次 commit + push

### ✔ 不要：

* 一次提交几百个文件
* 不写 commit message
* 长时间不 push

---

# 🧭 九、推荐习惯（工程化）

✔ 每天开发结束 push 一次
✔ 每个功能独立 commit
✔ commit 写清楚“做了什么”
✔ 不要把 build 文件上传 GitHub

---

# 🧠 十、核心一句话总结

```text
改代码 → git add → git commit → git push
```

---

如果你下一步想升级，我可以帮你做这个👇：

* 🧱 把 GO2 项目改成“标准ROS2工程结构”
* 🔄 做 Jetson + 笔记本 双端同步开发方案
* 🚀 给你搭一个“一键部署到机器人”的脚本系统

只要说一声 👍
