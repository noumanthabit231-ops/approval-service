# Approval Service

Сервис согласования контента перед публикацией. Принимает заявки, фиксирует решения (approve/reject/cancel), хранит аудит-лог всех изменений.

## Быстрый старт

### Локально

```bash
# Установка
cd approval-service
python -m venv .venv && source .venv/bin/activate  # или .venv\Scripts\activate на Windows
pip install -e ".[dev]"

# Запуск
uvicorn approval_service.main:app --reload --port 8000
```

### Docker

```bash
docker compose up --build
```

Сервис будет доступен на `http://localhost:8000`.

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка живости |
| GET | `/ready` | Проверка готовности (+ БД) |
| POST | `/api/v1/workspaces/{ws}/approval-requests` | Создать заявку |
| GET | `/api/v1/workspaces/{ws}/approval-requests` | Список заявок |
| GET | `/api/v1/workspaces/{ws}/approval-requests/{id}` | Одна заявка |
| POST | `/api/v1/workspaces/{ws}/approval-requests/{id}/approve` | Согласовать |
| POST | `/api/v1/workspaces/{ws}/approval-requests/{id}/reject` | Отклонить |
| POST | `/api/v1/workspaces/{ws}/approval-requests/{id}/cancel` | Отменить |

## Auth (заглушка)

Для локальной разработки каждый запрос должен содержать заголовки:

- `X-User-Id` — ID пользователя
- `X-User-Permissions` — список прав через запятую

Доступные права:

| Действие | Когда нужно |
|----------|-------------|
| `approval:read` | Чтение заявок |
| `approval:create` | Создание заявки |
| `approval:decide` | Approve / Reject |
| `approval:cancel` | Cancel |

Пример:

```bash
curl -H "X-User-Id: usr_1" \
     -H "X-User-Permissions: approval:read,approval:create,approval:decide,approval:cancel" \
     -H "Content-Type: application/json" \
     -d '{"sourceType":"publication","sourceId":"pub_1","title":"Test","reviewerUserIds":["usr_2"]}' \
     http://localhost:8000/api/v1/workspaces/ws_1/approval-requests
```

При отсутствии `X-User-Permissions` все права предоставляются по умолчанию (для удобства локальной разработки).

## Тесты

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `APP_DATABASE_URL` | `sqlite+aiosqlite:///./approval.db` | URL базы данных |
| `APP_LOG_LEVEL` | `INFO` | Уровень логирования |

## Миграции

```bash
# Создать новую миграцию
alembic revision --autogenerate -m "description"

# Применить
alembic upgrade head
```
