# DESIGN.md — Approval Service

## Модель данных

Две таблицы:

### `approval_requests`

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | String(12) | Первичный ключ, генерируется (`uuid4().hex[:12]`) |
| `workspace_id` | String(64) | ID workspace, индекс |
| `source_type` | String(32) | Тип контента: publication, scenario, edit, external |
| `source_id` | String(64) | Внешний ID контента |
| `title` | String(255) | Заголовок заявки |
| `description` | Text | Описание |
| `reviewer_user_ids` | JSON | Список ID рецензентов |
| `status` | String(16) | Статус: pending, approved, rejected, cancelled |
| `idempotency_key` | String(128) | Ключ идемпотентности, уникален в рамках workspace |
| `created_by` | String(64) | Кто создал |
| `created_at` | DateTime | Когда создана |
| `updated_at` | DateTime | Когда обновлена |

Уникальное ограничение: `(workspace_id, idempotency_key)`.

### `audit_entries`

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | Integer | Автоинкремент |
| `request_id` | FK → approval_requests.id | Ссылка на заявку |
| `workspace_id` | String(64) | Денормализованный workspace для индексации |
| `action` | String(32) | Действие: created, approved, rejected, cancelled |
| `actor` | String(64) | Кто совершил действие |
| `details` | JSON | Детали (comment / reason) |
| `created_at` | DateTime | Когда совершено |

## Границы сервиса

Сервис отвечает только за процесс согласования. Внешние сущности (publication, scenario, edit, external, пользователи, workspace) передаются как идентификаторы. Сервис не знает и не проверяет их существование — это зона ответственности вызывающей стороны.

## Обработка повторов (Idempotency)

Клиент опционально передаёт `idempotencyKey` при создании заявки. Если заявка с таким ключом уже существует в рамках workspace — возвращается существующая (201, без создания дубля).

Уникальность обеспечена constraint `uq_workspace_idempotency` на уровне БД.

Если ключ не передан — каждый POST создаёт новую заявку.

## Изоляция workspace

Все запросы параметризованы `workspace_id` в URL. На уровне БД каждый запрос фильтруется по `workspace_id`. Данные одного workspace недоступны из другого.

## Аудит

Каждое изменение состояния заявки записывает `AuditEntry` с указанием:
- кто совершил действие (`actor`)
- что именно сделал (`action`)
- детали (comment / reason)

Аудит-записи возвращаются в составе ответа `GET /.../{request_id}` как поле `auditEntries`.

## События / Интеграции

Сервис содержит встроенный event bus (`events.py`). После каждого изменения публикуются события:

- `approval_request.created` — при создании заявки
- `approval_request.status_changed` — при изменении статуса

Подписчики регистрируются через `events.subscribe(async_handler)`. В текущей версии события только логируются. Для продакшена замените на Kafka / RabbitMQ / Redis PubSub.

Все публикуемые payload'ы проходят санитизацию — ключи, содержащие `token`, `secret`, `password`, `email`, `key`, `url`, `credential`, исключаются из событий и логов.

## Известные компромиссы

1. **SQLite** для локального запуска. В production — заменить на PostgreSQL (достаточно сменить `APP_DATABASE_URL`). Миграции Alembic готовы к обеим БД.

2. **Auth-заглушка** — заголовки без JWT/OAuth. Для продакшена заменить `dependencies.py:get_auth_context` на проверку реального токена.

3. **In-process event bus** — для реальной интеграции заменить на внешний брокер сообщений.

4. **Отсутствие пагинации на основе курсора** — `OFFSET/LIMIT` достаточно для MVP. При большом объёме данных — перейти на cursor-based pagination.

5. **Нет软кого удаления (soft delete)** — заявки не удаляются, только переводятся в финальный статус. При необходимости добавить поле `deleted_at`.

6. **Синхронный API** — все операции атомарны и возвращают результат сразу. Долгоиграющие процессы (если появятся) стоит вынести в фоновые задачи.
