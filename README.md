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
- **智能点餐助手**：基于大模型的真实对话（百炼 DeepSeek）+ RAG 知识库（店铺/菜品/FAQ）+ 图片搜菜（智谱视觉模型）；
- **账号体系**：默认管理员账号 `root` / `123456`，首次登录后强制修改密码；
- **后端架构**：API → Service → Repository → Model，依赖 MySQL + Redis + MongoDB。

> 说明：顾客端“智能点餐助手”已接入真实大模型（见[核心功能](#核心功能)），传统点餐链路（购物车下单等）走传统 `POST /api/v1/order` 接口，两者完全解耦。相关 AI 配置见[配置说明](#配置说明)。

---

## 技术栈

| 层级   | 技术                                                            |
| ------ | --------------------------------------------------------------- |
| 前端   | Vue 3 + Vite + TypeScript + Element Plus + Pinia + Vue Router   |
| 后端   | FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2                  |
| 数据库 | MySQL 8.0+                                                      |
| 文档库 | MongoDB（AI 聊天历史）                                          |
| 缓存   | Redis（图片验证码）                                             |
| 导出   | reportlab（PDF）                                                |
| 人脸识别 | face_recognition（dlib）                                       |
| AI 框架 | LangChain 1.3 + LangGraph（Agent 运行时）                        |
| 大语言模型 | 阿里云百炼 deepseek-v4-flash（OpenAI 兼容接口，已关闭思考模式）；混合意图"餐厅经理"专用更强模型 qwen3.7-plus（`BAILIAN_LLM_MODEL_X`）|
| 视觉模型 | 智谱 GLM-4V-Flash（图片搜菜）                                    |
| 向量模型 | 智谱 Embedding-3（512 维）+ Chroma 向量库 + 轻量 BM25 混合检索   |

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- Redis
- MongoDB（AI 聊天历史存储）
- Docker（可选，`scripts/start.py` 会自动启动 mysql-server / redis-server / mongo-server 容器）

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
# 是否部署模式
#   false=开发模式：MySQL/Redis/MongoDB 使用代码内置的本地默认配置，无需填写连接信息；
#         大模型 API Key 从【系统环境变量】读取
#   true =部署模式：数据库连接与大模型 API Key 从【本文件】读取
#   模型名称（型号）两种模式均从【本文件】读取，无默认值
IS_SERVER=false

# JWT 配置（⚠️ 重要：生产环境必须修改为随机强密钥！）
JWT_SECRET_KEY=your-secret-key-change-in-production
```

> 配置读取优先级：`.env` 文件 > 系统环境变量 > 代码默认值（`.env` 中没有的键才回退到环境变量）。
> 开发模式下 MySQL 固定为 `root/123456@localhost:3306`、Redis/MongoDB 为本地默认端口无密码，无需在 `.env` 配置连接信息。
> 大模型 API Key / 型号无默认值；取不到或调用失败（欠费、网络异常）时，AI 聊天会自动返回友好兜底回复，传统点餐功能不受影响。
> 本地开发需将 API Key 设为系统环境变量（如 `setx DASHSCOPE_API_KEY "sk-..."`、`setx ZHIPU_API_KEY "..."`），型号直接填在本文件中。

### 4. 初始化数据库

`scripts/init.sql` 是唯一的初始化脚本（建库、建表、插入初始菜单与管理员账号），应用启动时**不会**自动建库建表。部署时手动执行一次：

```bash
mysql -u root -p < scripts/init.sql
```

该脚本会删除并重建 `meiwei_bot` 数据库，创建表结构、初始菜单数据和管理员账号（`root` / `123456`）。

> 后端启动时会做依赖自检：**MySQL 为强校验**（连不上或未执行 `init.sql` 导致表缺失时拒绝启动），**MongoDB 为强校验**（AI 聊天历史必需依赖），**Redis 为软校验**（连不上仅告警，验证码降级为内存缓存）。首次部署若漏掉本步骤，启动时会直接报错提醒。

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
python scripts/start.py

# 生产模式：构建前端并作为静态资源由后端 served
python scripts/start.py --prod
```

启动后访问：

| 服务              | 地址                          |
| ----------------- | ----------------------------- |
| 前端（开发模式）  | http://localhost:5173         |
| 后端 API          | http://127.0.0.1:8000         |
| API 文档（Swagger）| http://127.0.0.1:8000/docs    |
| API 文档（ReDoc）  | http://127.0.0.1:8000/redoc   |

> `scripts/start.py` 会自动检查并清理被占用的 `8000` / `5173` 端口，Windows 下还会将控制台编码设为 UTF-8。

---

## 项目结构

```
multimodal-smart-restaurant/
├── scripts/                  # 一键启动、init.sql 初始化、AI 连通性/路由校准/经理冒烟测试脚本
├── README.md
├── .gitignore
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── main.py           # 应用入口
│   │   ├── core/             # 配置、数据库、日志、异常
│   │   ├── models/           # SQLAlchemy ORM 模型
│   │   ├── schemas/          # Pydantic 数据模型
│   │   ├── repositories/     # 数据访问层
│   │   ├── services/         # 业务逻辑层（认证、验证码、人脸、菜单、订单）
│   │   ├── api/              # API 路由（deps.py 依赖注入 + v1/ 版本化路由）
│   │   ├── utils/            # 工具（文本格式化、PDF 导出）
│   │   └── ai/               # 智能聊天模块（独立子目录，传统代码只被调用不被修改）
│   │       ├── router.py     # /api/v1/ai/chat、/chat/stream（SSE 流式）
│   │       ├── config.py     # AI 配置读取（.env 优先，环境变量兜底，占位符视为未设置；双模型强绑定校验）
│   │       ├── schemas.py    # AI 模块请求/响应模型
│   │       ├── image_search.py  # 图片搜菜：视觉识别 + 菜单比对
│   │       ├── chat_store.py   # 聊天历史持久化（MongoDB，必需依赖，启动强校验）
│   │       ├── sanitize.py     # 输出净化（确定性移除表情符号与“（微笑）”类舞台指示）
│   │       ├── llm/          # 模型客户端（bailian.py 文本对话，基础+更强双模型工厂 / zhipu.py 视觉）
│   │       ├── rag/          # RAG 知识库（loader/retriever/manager/sync_dishes）
│   │       │   ├── data/     # 知识文档（store/dishes/faq/policy，dishes 由数据库同步生成）
│   │       │   └── vectorstore/   # Chroma 持久化产物（运行生成，不提交）
│   │       └── agent/        # 点餐多智能体（分级意图路由）
│   │           ├── fastpath.py    # L1 正则快速路：整句完全匹配的简单意图确定性处理（加/减/换菜、清空、下单、查订单）
│   │           ├── graph.py       # L2 LangGraph 多智能体图：router 分类节点 -> 购物车/订单/资讯/闲聊专员 + 餐厅经理（混合意图）
│   │           ├── prompts/       # 各角色提示词（router/cart/order/knowledge/chitchat/manager.md）
│   │           ├── context.py     # 请求级上下文（db / user_id / 购物车快照）
│   │           └── tools/         # 工具层（菜单检索 / 购物车增删改 / 下单与订单查询 / RAG 检索）
│   ├── static/               # 静态资源目录（保留挂载，当前无内容）
│   ├── tests/                # 测试用例（API 测试 + 订单服务/AI 智能体/AI 配置单元测试）
│   ├── .env                  # 环境变量（不提交）
│   ├── pyproject.toml        # 项目元数据与 ruff/mypy 配置
│   └── requirements.txt      # 后端依赖（固定版本）
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
- 超级管理员 `rootroot`：首次登录强制改密（不允许改回初始密码，且仅允许修改一次）；超管未改初始密码期间项目处于“未启用”状态，其他账号登录一律提示“项目未启用，请联系开发人员”；超管面板可重置 root 密码、查看/充值普通用户的智能聊天次数、删除用户

### 智能点餐助手（AI 模块）

独立子目录 `backend/app/ai/`，与传统后端完全解耦（传统代码只被调用、不被修改）：

- **文本对话**：百炼 deepseek-v4-flash（已用 `enable_thinking=false` 关闭思考模式防思维链泄漏），分级意图路由：L1 正则快速路处理简单确定的意图（如“来三份宫保鸡丁”“清空购物车”“确认下单”“最近5条订单”），不调 LLM；复杂意图进入 L2 多智能体图——router 分类节点（只看本句）分发到购物车专员（含下单）/ 订单查询专员 / 资讯顾问 / 闲聊节点 / **餐厅经理**；一句话混合多个类别诉求（如“营业时间是什么，再来一份麻婆豆腐和两份宫保鸡丁”）路由到餐厅经理：装备全部专员工具、使用更强模型（`BAILIAN_LLM_MODEL_X`）一站式办妥；写操作同样只认本句（工具层硬校验与专员一致），查询可结合历史；操作过多过杂或矛盾则整体拒绝、走 unclear 请用户拆分说清楚（宁愿不做，不可做错）
- **对话操作购物车/订单**：工具层复用传统后端服务（只调用不修改），下单由 `order_service.create_order` 服务端校验兜底；**增删改/下单等写操作只依据用户当前这句话**，指代历史内容（如“刚才那个菜再来一份”）一律请用户一句话说清楚，不得猜测执行；工具层另有确定性硬校验（`guard_write_op`）：句中未明确提及的菜品/动作直接拒绝执行，即使上一轮是 AI 给出的选项、用户只回“移除/好的”也不算数；被拒绝时 AI 必须如实说明未执行，不得声称“已下单/已移除”；**查询（购物车/订单/FAQ）为只读，可结合对话历史理解指代**；购物车通过 SSE `done` 事件快照回传前端落地；**每道菜辣度为商家设定的固定属性**（菜单标注即出餐辣度），AI 不得向顾客确认辣度或将其写入订单备注，顾客要求调辣时如实告知不可调整并建议其他菜；回复出口确定性移除表情符号与“（微笑）”类舞台指示标注
- **聊天次数配额**：普通用户初始 100 次发送额度，耗尽弹窗提示“次数不足，请联系开发人员”；超管面板可查看剩余次数并充值（+100/次）
- **对话历史与滚动摘要**：MongoDB（独立库 `meiwei_ai`）按用户持久化；MongoDB 与 MySQL 同为必需依赖，启动时强校验连通性；原始消息超过 20 条时，后台异步将最旧 10 条压缩为滚动摘要（≤300 字，保留偏好/忌口/菜品/订单结论），进 prompt 时“摘要 + 最近 10 条原文”一起注入；前端“清空对话”会同步删除该用户的全部聊天记录与摘要
- **RAG 知识库**：店铺介绍/营业信息/FAQ/配送政策 + 39 道菜品文档（由数据库同步生成，保证单一事实源）；**菜品文档不含价格与库存**——动态数据一律由 `search_dish` 实时查询数据库，避免快照滞后；Chroma 向量检索 + BM25 关键词混合召回；启动时自动重建、商家改菜单后指纹轮询（5 分钟）自动重建、重建期间检索请求持锁排队；由资讯顾问以 `search_knowledge` 工具按需调用
- **图片搜菜**：智谱 GLM-4V-Flash 识别图片 → 是菜品则结合真实菜单由大模型比对推荐；不是菜品则提示重新上传
- **SSE 流式输出**：GPT 风格打字机逐字渲染（SSE 原文进缓冲，前端 24ms 一帧匀速显示、积压自动加速），前端聊天页（机器人头像 + 语音播报开关）
- **语音播报**：浏览器内置 speechSynthesis（Web Speech API），零后端依赖；SSE 流式文本按句切分即时报播，句间由浏览器原生队列连续播放
- **语音输入**：输入框左侧麦克风按钮，浏览器 SpeechRecognition 实时转文字填入输入框；开始录音自动打断播报，4 秒无声音自动停止

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
| POST   | `/api/v1/ai/chat`                | 智能聊天（同步） |
| POST   | `/api/v1/ai/chat/stream`         | 智能聊天（SSE 流式，支持图片搜菜） |
| DELETE | `/api/v1/ai/chat/history`        | 清空当前用户的聊天记录（MongoDB） |
| GET    | `/api/v1/admin/menu`             | 商家菜品管理     |
| GET    | `/api/v1/admin/orders`           | 商家订单管理     |
| POST   | `/api/v1/admin/reset-root-password` | 超管：重置 root 密码 |
| GET    | `/api/v1/admin/user-quotas`      | 超管：用户聊天次数列表 |
| POST   | `/api/v1/admin/user-quotas/{id}/recharge` | 超管：充值 100 次 |
| DELETE | `/api/v1/admin/users/{id}`       | 超管：删除普通用户 |

完整接口文档见启动后的 Swagger UI：`http://127.0.0.1:8000/docs`

---

## 配置说明

编辑 `backend/.env`：

```env
# ==================== 模式开关 ====================
# false=开发模式：MySQL/Redis/MongoDB 使用代码内置的本地默认配置
#   （MySQL root/123456@localhost:3306，Redis localhost:6379 无密码，MongoDB localhost:27017 无密码），
#   下面三个连接 URL 不生效，无需配置
# true=部署模式：使用下面的 DATABASE_URL/REDIS_URL/MONGODB_URL（含用户名/密码/端口）
IS_SERVER=false

# ==================== 数据库连接（仅部署模式生效）====================
# MySQL，格式: mysql+aiomysql://用户名:密码@主机:端口/库名
DATABASE_URL=mysql+aiomysql://root:123456@localhost:3306/meiwei_bot

# Redis（验证码缓存），无认证: redis://主机:端口/库序号；有认证: redis://用户名:密码@主机:端口/库序号
REDIS_URL=redis://localhost:6379/0

# MongoDB（AI 聊天历史存储，必需依赖，后端启动时强校验连通性）
# 无认证: mongodb://主机:端口；有认证: mongodb://用户名:密码@主机:端口
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB=meiwei_ai
AI_CHAT_HISTORY_LIMIT=10

# JWT 配置（⚠️ 重要：生产环境必须修改为随机强密钥！）
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_HOURS=24

# 日志级别（可选）
LOG_LEVEL=INFO

# 生产模式（可选，scripts/start.py --prod 会自动设置）
# SERVE_STATIC=true
# FRONTEND_DIST_DIR=../frontend/dist
# CORS_ORIGINS=https://example.com
# CORS_ALLOW_CREDENTIALS=false

# ==================== AI 模型配置 ====================
# API Key：开发模式读系统环境变量，部署模式读本文件（占位符视为未配置），无默认值
# 模型名称（型号）：开发与部署均读本文件，无默认值
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
# 更强模型（混合意图"餐厅经理"专用），与 BAILIAN_LLM_MODEL 强绑定：
# 配置了 BAILIAN_LLM_MODEL 就必须配置本项，否则后端启动直接报错，不做降级
BAILIAN_LLM_MODEL_X=qwen3.7-plus-2026-05-26
BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

> AI 连通性验证脚本：`scripts/test_zhipu_embedding.py`、`scripts/test_zhipu_vision.py`、`scripts/test_bailian_llm.py`、`scripts/test_bailian_llm_x.py`（更强模型，含参数兼容性与流式验证）、`scripts/test_router.py`（路由分类边界实测校准）、`scripts/test_manager_agent.py`（餐厅经理端到端冒烟，真实调用模型与数据库）（自动从 `backend/.env` 读取对应 Key）。

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
pip install pytest pytest-asyncio httpx aiosqlite

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

### 使用 scripts/start.py 一键部署

```bash
python scripts/start.py --prod
```

生产模式会：

1. 自动检查 Node.js 环境；
2. 执行 `npm run build` 构建前端；
3. 让 FastAPI 在 `8000` 端口同时提供 API 与静态文件服务。

启动时依赖自检：MySQL / MongoDB 为强校验（连不上或表缺失则拒绝启动），Redis 为软校验（连不上降级为内存缓存并告警），向量库缺失或菜单变更时自动重建。

### 手动部署

```bash
cd frontend
npm install
npm run build

cd ../backend
# 设置环境变量后启动
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> 生产环境建议通过 Nginx / Caddy 反向代理，并配置 HTTPS。

---

## 常见问题

### Q：启动时提示端口 8000 被占用？

`python scripts/start.py` 会自动尝试结束占用 8000 的进程。若失败，可手动结束：

```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# macOS / Linux
lsof -ti:8000 | xargs kill -9
```

### Q：Windows 控制台日志显示乱码？

`scripts/start.py` 已自动设置 `chcp 65001` 与 Python UTF-8 编码。若仍有乱码，请确保终端字体支持中文（如 Microsoft YaHei、Consolas）。

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

### Q：知识库/向量库如何更新？

- **启动时自动处理**：向量库缺失（如新部署）或菜单指纹变化时自动重建，无需人工干预；
- **商家修改菜品**：后台任务每 5 分钟轮询菜单指纹（数量 + 最大更新时间），变化即自动同步菜品文档并重建向量库；
- **手工修改静态文档**（`rag/data/store|faq|policy/`）：指纹管不到，需手动重建：`cd backend && python -m app.ai.rag.loader`，或删除 `vectorstore/` 目录后重启后端。
