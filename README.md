# 多模态智能餐厅系统

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![Vue.js](https://img.shields.io/badge/Vue-3.x-green)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688)](https://fastapi.tiangolo.com/)

> 一个基于 **FastAPI + Vue 3** 的在线点餐与商家管理系统。支持菜单浏览、购物车、订单管理、商家后台、图片验证码、人脸登录等功能。

---

## 目录

- [项目简介](#项目简介)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [核心功能](#核心功能)
- [API 概览](#api-概览)
- [配置说明](#配置说明)
- [人脸登录依赖](#人脸登录依赖)
- [测试](#测试)
- [部署](#部署)
- [常见问题](#常见问题)

---

## 项目简介

“美味餐厅”点餐系统提供完整的在线点餐与商家管理能力：

- **顾客端**：浏览菜单、管理购物车、提交订单、查看订单（导出 PDF）、管理个人资料、录入人脸；
- **商家端**：管理菜品、查看订单（显示脱敏用户名，如 `刘**`）、导出订单（PDF 含用户ID与脱敏用户名）；
- **登录方式**：账号密码登录（带图片验证码）+ 人脸登录（仅存 128 维特征向量，不保存人脸照片）；
- **账号体系**：默认管理员账号 `root` / `123456`，首次登录后强制修改密码；
- **后端架构**：API → Service → Repository → Model，依赖 MySQL + Redis。

> 说明：顾客端“智能点餐助手”聊天界面目前为保留的 UI 占位壳子，后端 `/chat` 接口已移除（购物车下单走传统 `POST /api/v1/order` 接口），后续接入真实 LLM 时再另行设计，相关 AI 配置见[配置说明](#配置说明)。

---

## 技术栈

| 层级   | 技术                                                            |
| ------ | --------------------------------------------------------------- |
| 前端   | Vue 3 + Vite + TypeScript + Element Plus + Pinia + Vue Router   |
| 后端   | FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2                  |
| 数据库 | MySQL 8.0+                                                      |
| 缓存   | Redis（图片验证码）                                             |
| 导出   | reportlab（PDF）                                                |
| 人脸识别 | face_recognition（dlib）                                       |

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- Redis
- Docker（可选，`start.py` 会自动启动 mysql-server / redis-server 容器）

### 1. 克隆项目

```bash
git clone https://github.com/user20421/multimodal-smart-restaurant.git
cd multimodal-smart-restaurant
```

### 2. 安装后端依赖

```bash
# 使用 conda 环境 mmsr（推荐）
conda activate mmsr

cd backend
pip install -r requirements.txt
```

> 人脸识别依赖 dlib，Windows 上建议先通过 conda 安装：
> ```bash
> conda install -c conda-forge dlib
> ```

### 3. 配置环境变量

在 `backend/` 目录下创建 `.env` 文件：

```env
# 数据库配置
DATABASE_URL=mysql+aiomysql://root:123456@localhost:3306/meiwei_bot

# Redis 配置（用于图片验证码缓存）
REDIS_URL=redis://localhost:6379/0

# JWT 配置（⚠️ 重要：生产环境必须修改为随机强密钥！）
JWT_SECRET_KEY=your-secret-key-change-in-production

# 调试模式（可选）
DEBUG=false
```

### 4. 初始化数据库

```bash
cd ..
python scripts/init_database.py
```

该脚本会删除并重建 `meiwei_bot` 数据库，执行 `rawfiles/sql/init.sql`，创建表结构、初始菜单数据和管理员账号。

### 5. 安装前端依赖

```bash
cd frontend
npm install
```

### 6. 启动服务

```bash
# 回到项目根目录
cd ..

# 开发模式：同时启动前后端
python start.py

# 生产模式：构建前端并作为静态资源由后端 served
python start.py --prod
```

启动后访问：

| 服务              | 地址                          |
| ----------------- | ----------------------------- |
| 前端（开发模式）  | http://localhost:5173         |
| 后端 API          | http://127.0.0.1:8001         |
| API 文档（Swagger）| http://127.0.0.1:8001/docs    |
| API 文档（ReDoc）  | http://127.0.0.1:8001/redoc   |

> `start.py` 会自动检查并清理被占用的 `8001` / `5173` 端口，Windows 下还会将控制台编码设为 UTF-8。

---

## 项目结构

```
multimodal-smart-restaurant/
├── start.py                  # 一键启动脚本（开发 / 生产）
├── README.md
├── .gitignore
├── rawfiles/
│   └── sql/                  # 数据库初始化 SQL
├── scripts/
│   ├── init_database.py      # 删除并重建数据库
│   ├── test_db.py            # 数据库连通性测试
│   ├── verify_captcha_e2e.py # 验证码端到端测试
│   ├── test_zhipu_embedding.py  # 智谱 Embedding-3 向量模型测试
│   ├── test_zhipu_vision.py     # 智谱 GLM-4V-Flash 视觉模型测试
│   ├── test_bailian_llm.py      # 阿里云百炼 DeepSeek LLM 测试
│   └── 扩散模型.jpg          # 视觉模型测试图片
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── main.py           # 应用入口
│   │   ├── core/             # 配置、数据库、日志、异常、种子数据
│   │   ├── models/           # SQLAlchemy ORM 模型
│   │   ├── schemas/          # Pydantic 数据模型
│   │   ├── repositories/     # 数据访问层
│   │   ├── services/         # 业务逻辑层（认证、验证码、人脸、菜单、订单、初始化）
│   │   ├── api/              # API 路由（deps.py 依赖注入 + v1/ 版本化路由）
│   │   └── utils/            # 工具（文本格式化、PDF 导出）
│   ├── static/               # 静态资源目录（保留挂载，当前无内容）
│   ├── tests/                # 测试用例（API 测试 + 订单服务单元测试）
│   ├── .env                  # 环境变量（不提交）
│   ├── pyproject.toml        # 项目元数据与 ruff/mypy 配置
│   ├── requirements.txt      # 生产依赖
│   └── requirements-dev.txt  # 开发/测试依赖
│
└── frontend/                 # Vue 3 前端
    ├── src/
    │   ├── app/              # 应用入口、布局、路由
    │   ├── features/         # 业务功能（认证、聊天、菜单、订单、购物车等）
    │   ├── modules/admin/    # 商家后台
    │   ├── shared/           # 共享 API、类型、常量、工具
    │   └── views/            # 页面视图
    ├── package.json
    └── vite.config.ts
```

---

## 核心功能

### 顾客端

- 菜单浏览
- 购物车管理（加减数量、清空）
- 提交订单、查看我的订单（分页、导出 PDF）
- 个人资料管理（手机号、性别、出生日期）
- 人脸录入与人脸登录

### 商家端

- 商品管理（增删改查、辣度设置）
- 订单管理（分页、导出 PDF，含用户ID与脱敏用户名）
- 待处理订单（显示脱敏用户名）
- 全部订单导出

### 认证与安全

- 账号密码登录 + 图片验证码
- 人脸登录（基于 `face_recognition`，仅存 128 维特征向量，不落盘保存照片）
- JWT Token 鉴权
- 订单接口返回的用户名统一脱敏（仅保留首字，如 `刘**`）
- 默认管理员 `root` / `123456` 首次登录强制修改密码

---

## API 概览

| 方法   | 路径                             | 说明             |
| ------ | -------------------------------- | ---------------- |
| POST   | `/api/v1/auth/register`          | 注册             |
| POST   | `/api/v1/auth/login`             | 账号密码登录     |
| POST   | `/api/v1/auth/face-login`        | 人脸登录         |
| POST   | `/api/v1/auth/face-register`     | 录入/更新人脸    |
| GET    | `/api/v1/auth/captcha`           | 获取图片验证码   |
| POST   | `/api/v1/auth/change-password`   | 修改密码         |
| GET    | `/api/v1/auth/profile`           | 获取个人资料     |
| PUT    | `/api/v1/auth/profile`           | 更新个人资料     |
| GET    | `/api/v1/menu`                   | 获取菜单         |
| POST   | `/api/v1/order`                  | 创建订单         |
| GET    | `/api/v1/orders`                 | 我的订单（分页） |
| GET    | `/api/v1/admin/menu`             | 商家菜品管理     |
| GET    | `/api/v1/admin/orders`           | 商家订单管理     |

完整接口文档见启动后的 Swagger UI：`http://127.0.0.1:8001/docs`

---

## 配置说明

编辑 `backend/.env`：

```env
# 数据库配置
DATABASE_URL=mysql+aiomysql://root:123456@localhost:3306/meiwei_bot

# Redis 配置（验证码缓存）
REDIS_URL=redis://localhost:6379/0

# JWT 配置（⚠️ 重要：生产环境必须修改为随机强密钥！）
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_HOURS=24

# 日志级别（可选）
LOG_LEVEL=INFO

# 调试模式（可选）
DEBUG=false

# 生产模式（可选，start.py --prod 会自动设置）
# SERVE_STATIC=true
# FRONTEND_DIST_DIR=../frontend/dist
# CORS_ORIGINS=https://example.com
# CORS_ALLOW_CREDENTIALS=false

# ==================== AI 模型配置（可选，供后续智能功能使用）====================
# 智谱 AI（⚠️ 部署时请手动设置真实 Key）
# 获取地址: https://bigmodel.cn/usercenter/proj-mgmt/apikeys
ZHIPU_API_KEY=your-zhipu-api-key-here
ZHIPU_EMBEDDING_MODEL=embedding-3      # 向量模型
ZHIPU_EMBEDDING_DIMENSIONS=512
ZHIPU_VISION_MODEL=glm-4v-flash        # 视觉模型（免费）

# 阿里云百炼（⚠️ 部署时请手动设置真实 Key）
# 获取地址: https://bailian.console.aliyun.com/#/api-key
DASHSCOPE_API_KEY=your-dashscope-api-key-here
BAILIAN_LLM_MODEL=deepseek-v4-flash-0731
BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

> AI 连通性验证脚本：`scripts/test_zhipu_embedding.py`、`scripts/test_zhipu_vision.py`、`scripts/test_bailian_llm.py`（需先设置对应环境变量）。

---

## 人脸登录依赖

后端使用 `face_recognition` 库进行人脸特征提取与比对，底层依赖 `dlib`。

- Linux / macOS：直接 `pip install face_recognition` 即可。
- Windows：建议先通过 conda 安装 dlib：
  ```bash
  conda install -c conda-forge dlib
  pip install face_recognition
  ```

> 注意：`face_recognition_models` 依赖 `pkg_resources`，因此 `setuptools` 需要 `<70`，已在 `requirements.txt` 中限定。

---

## 测试

### 后端测试

```bash
cd backend

# 安装测试依赖（首次）
pip install -r requirements-dev.txt

# 全部测试
pytest tests
```

### 前端检查

```bash
cd frontend

# TypeScript 类型检查
npm run type-check

# 生产构建
npm run build
```

---

## 部署

### 使用 start.py 一键部署

```bash
python start.py --prod
```

生产模式会：

1. 自动检查 Node.js 环境；
2. 执行 `npm run build` 构建前端；
3. 让 FastAPI 在 `8001` 端口同时提供 API 与静态文件服务。

### 手动部署

```bash
cd frontend
npm install
npm run build

cd ../backend
# 设置环境变量后启动
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

> 生产环境建议通过 Nginx / Caddy 反向代理，并配置 HTTPS。

---

## 常见问题

### Q：启动时提示端口 8001 被占用？

`python start.py` 会自动尝试结束占用 8001 的进程。若失败，可手动结束：

```bash
# Windows
netstat -ano | findstr :8001
taskkill /PID <PID> /F

# macOS / Linux
lsof -ti:8001 | xargs kill -9
```

### Q：Windows 控制台日志显示乱码？

`start.py` 已自动设置 `chcp 65001` 与 Python UTF-8 编码。若仍有乱码，请确保终端字体支持中文（如 Microsoft YaHei、Consolas）。

### Q：MySQL 8 连接提示 caching_sha2_password 错误？

请安装 `cryptography` 包（已加入 `requirements.txt`）：

```bash
pip install cryptography
```

### Q：人脸识别登录失败？

请确认：

1. 已正确安装 `dlib` 和 `face_recognition`；
2. 已在“用户设置”页录入人脸；
3. 登录时光线充足、面部正对摄像头。

### Q：人脸照片保存在哪里？

不保存照片。录入时仅在内存中提取 128 维特征向量并存入 `users.face_encoding` 字段（JSON），图片用完即弃，避免隐私泄露。

### Q：为什么数据库里订单时间与本地时间差 8 小时？

Docker 中的 MySQL 默认使用 UTC 时区，`created_at` 存的是 UTC 时间。本项目约定**数据库配置不动、使用侧统一转换**：`OrderOut` / `MenuItemOut` schema 在序列化输出时通过 `app.utils.formatters.utc_to_local()` 转为东八区时间（API 返回与 PDF 导出均自动生效），商家仪表盘“今日统计”查询也会先将本地日期边界换算为 UTC 再比较。
