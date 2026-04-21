# Shared Dependencies

Cross-file contract manifest. Populated by the Architect Agent during pipeline setup and updated after each Coder task completes. Every Coder invocation receives this file as context.

---

## Shared Types & Models

<!-- Pydantic models, TypedDicts, dataclasses, and Protocol classes used across more than one file. -->
<!-- Format: class name, source module, field names and types. -->

_Populated by Architect Agent (AGT-02)._

---

## Exported Function Signatures

<!-- Public functions exported from one module and imported by another. -->
<!-- Format: function name, source module, parameter types, return type. -->

_Populated by Architect Agent (AGT-02) and updated after each Coder task._

---

## API Contracts

<!-- REST endpoint definitions: method, path, request body schema, response schema, status codes. -->

_Populated by Architect Agent (AGT-02)._

---

## Data Schemas

<!-- Database models, JSON schemas, and any persistent data structures. -->
<!-- Include field names, types, constraints, and relationships. -->

_Populated by Architect Agent (AGT-02)._

---

## Environment Variables

<!-- All env vars the application reads. Name, type, required/optional, description. -->
<!-- These are loaded via config.py — never accessed directly with os.environ outside that module. -->

| Variable | Type | Required | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | string | yes | Anthropic API key for all Claude calls |
| `E2B_API_KEY` | string | yes | e2b.dev sandbox execution |
| `GITHUB_PAT` | string | yes | GitHub personal access token (repo scope only) |

_Additional variables added by Architect Agent (AGT-02) based on project brief._

---

## File Registry

<!-- Tracks every generated file: path, owning module, and its exported public interface. -->
<!-- Updated after each Coder task completes (Ralph Loop step 5). -->
<!-- Coder reads this to get dependency signatures without receiving full source code. -->

| File Path | Module | Exported Interface |
|---|---|---|

_Populated progressively as Coder tasks complete._

---

### `main.py`

### Functions
def get_db_connection()
def init_database() -> None
def startup_event() -> None
def create_user(user_data: UserCreate) -> User
def get_user(user_id: int) -> User

### Classes
class UserCreate(BaseModel):
    name: str
    email: str

class User(BaseModel):
    id: int
    name: str
    email: str

### Module-Level Constants
app: FastAPI
DATABASE_PATH: str = "users.db"

---

### `main.py`

### Functions
def get_db_connection()
def init_database() -> None
def lifespan(app: FastAPI)
def startup_event() -> None
def create_user(user_data: UserCreate) -> User
def get_user(user_id: int) -> User

### Classes
class UserCreate:
    name: str
    email: str

class User:
    id: int
    name: str
    email: str

### Module-Level Constants
DATABASE_PATH: str = "users.db"
app: FastAPI

---

### `main.py`

### Functions
def get_db_connection() -> sqlite3.Connection
def init_database() -> None
async def lifespan(app: FastAPI)
def startup_event() -> None
def create_user(user_data: UserCreate) -> User
def get_user(user_id: int) -> User

### Classes
class UserCreate:
    name: str
    email: str

class User:
    id: int
    name: str
    email: str

### Module-Level Constants
DATABASE_PATH: str = "users.db"
app: FastAPI

---

### `main.py`

### Functions
def get_db_connection() -> sqlite3.Connection
def init_database() -> None
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict
async def lifespan(app: FastAPI)
def startup_event() -> None
def hash_password(password: str) -> str
def verify_password(password: str, hashed: str) -> bool
def sanitize_sql_input(value: str) -> str
def create_user(user_data: UserCreate) -> User
def get_user(user_id: int, current_user: dict = Depends(verify_token)) -> User
async def add_security_headers(request, call_next)

### Classes
class UserCreate:
    name: str
    email: EmailStr
    password: str
    def validate_name(cls, v)
    def validate_password(cls, v)

class User:
    id: int
    name: str
    email: str

### Module-Level Constants
EMAIL_PATTERN: re.Pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
NAME_PATTERN: re.Pattern = re.compile(r'^[a-zA-Z\s\-\']{1,100}$')
security: HTTPBearer = HTTPBearer()
DATABASE_PATH: str = "users.db"
app: FastAPI

---

### `main.py`

### Functions
def get_db_connection() -> sqlite3.Connection
def init_database() -> None
def lifespan(app: FastAPI)
def startup_event() -> None
def create_user(user_data: UserCreate) -> User
def get_user(user_id: int) -> User

### Classes
class UserCreate:
    name: str
    email: str

class User:
    id: int
    name: str
    email: str

### Module-Level Constants
DATABASE_PATH: str = "users.db"
app: FastAPI

---

### `main.py`

### Functions
def get_db_connection() -> sqlite3.Connection
def init_database() -> None
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict
def startup_event() -> None
def hash_password(password: str) -> str
def verify_password(password: str, hashed: str) -> bool
def sanitize_sql_input(value: str) -> str
async def add_security_headers(request: Request, call_next)
def create_user(user_data: UserCreate) -> User
def get_user(user_id: int, current_user: Dict = Depends(verify_token)) -> User

### Classes
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    def validate_name(cls, v)
    def validate_password(cls, v)

class User(BaseModel):
    id: int
    name: str
    email: str

### Module-Level Constants
EMAIL_PATTERN: re.Pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
NAME_PATTERN: re.Pattern = re.compile(r'^[a-zA-Z\s\-\']{1,100}$')
security: HTTPBearer = HTTPBearer()
DATABASE_PATH: str = "users.db"
app: FastAPI = FastAPI(title="Secure User API", description="A secure user management API", version="1.0.0", lifespan=lifespan)
