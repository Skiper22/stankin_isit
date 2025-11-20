from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import secrets

from fastapi import FastAPI, Depends, HTTPException, Response, Request, Cookie
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import SQLModel, Field, Session, create_engine, select


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "cpvp_ultra.db"

API_VERSION = "v1"

# ---- DB Models ----
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    login: str
    password_hash: str
    email: Optional[str] = None
    blocked: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Role(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class UserRole(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    role_id: int = Field(foreign_key="role.id", primary_key=True)


class Site(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    region: str


class EquipmentType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class Equipment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id")
    equipment_type_id: int = Field(foreign_key="equipmenttype.id")
    code: str
    name: str
    status: str = "active"
    commissioning_date: date


class Material(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    unit: str
    description: Optional[str] = None
    reject_percent: Optional[float] = 0.0


class Inventory(SQLModel, table=True):
    site_id: int = Field(foreign_key="site.id", primary_key=True)
    material_id: int = Field(foreign_key="material.id", primary_key=True)
    qty_on_hand: float = 0.0
    reorder_point: float = 0.0


class WorkOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id")
    type: str  # corrective/preventive
    status: str  # draft/pending/in_progress/running/done/closed (в демо используем new/in_progress/done/closed)
    priority: str  # low, normal, high
    title: str = "Заявка ТОиР"
    description: Optional[str] = None
    equipment_id: Optional[int] = Field(default=None, foreign_key="equipment.id")
    planned_date: Optional[date] = None
    assigned_team: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkOrderMaterial(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    work_order_id: int = Field(foreign_key="workorder.id")
    material_id: int = Field(foreign_key="material.id")
    qty_planned: float = 0.0
    qty_fact: float = 0.0


class WorkOrderComment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    work_order_id: int = Field(foreign_key="workorder.id")
    author_id: int = Field(foreign_key="user.id")
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProductionPlan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id")
    period: str  # '2025-11'
    status: str  # draft/published


class PlanItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="productionplan.id")
    product_name: str
    quantity: int


class Supplier(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    contact: Optional[str] = None


class PurchaseOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    supplier_id: int = Field(foreign_key="supplier.id")
    site_id: int = Field(foreign_key="site.id")
    status: str = "draft"  # draft/in_progress/done/cancelled
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str
    text: str
    severity: str = "info"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    meta: Optional[str] = None


engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})


def create_db_and_seed():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        # seed roles
        if not s.exec(select(Role)).all():
            s.add_all([
                Role(name="admin"),
                Role(name="planner"),
                Role(name="maintainer"),
                Role(name="procurement"),
            ])
        # seed users
        if not s.exec(select(User)).all():
            admin = User(login="admin", password_hash="admin", email="admin@example.com")
            s.add(admin)
            s.commit()
            s.refresh(admin)
            admin_role = s.exec(select(Role).where(Role.name == "admin")).first()
            if admin_role:
                s.add(UserRole(user_id=admin.id, role_id=admin_role.id))
        # seed sites
        if not s.exec(select(Site)).all():
            s.add_all([
                Site(name="Площадка А", region="ЦФО"),
                Site(name="Площадка B", region="ПФО")
            ])
        # seed equipment types
        if not s.exec(select(EquipmentType)).all():
            s.add_all([
                EquipmentType(name="Дробильная машина"),
                EquipmentType(name="Конвейер")
            ])
        s.commit()
        # seed equipment
        if not s.exec(select(Equipment)).all():
            et1 = s.exec(select(EquipmentType).where(EquipmentType.name == "Дробильная машина")).first()
            et2 = s.exec(select(EquipmentType).where(EquipmentType.name == "Конвейер")).first()
            site1 = s.exec(select(Site).where(Site.name == "Площадка А")).first()
            site2 = s.exec(select(Site).where(Site.name == "Площадка B")).first()
            s.add_all([
                Equipment(
                    site_id=site1.id,
                    equipment_type_id=et1.id,
                    code="EQ-1001",
                    name="Дробилка-1",
                    status="active",
                    commissioning_date=date(2023, 5, 1)
                ),
                Equipment(
                    site_id=site2.id,
                    equipment_type_id=et2.id,
                    code="EQ-2001",
                    name="Конвейер-1",
                    status="maintenance",
                    commissioning_date=date(2024, 3, 15)
                ),
            ])
        # seed materials
        if not s.exec(select(Material)).all():
            s.add_all([
                Material(name="Подшипник 6206", unit="pcs", reject_percent=0.5),
                Material(name="Ремень приводной", unit="pcs", reject_percent=1.0),
            ])
        s.commit()
        # seed inventory
        mats = s.exec(select(Material)).all()
        sites = s.exec(select(Site)).all()
        for si in sites:
            for m in mats:
                if not s.get(Inventory, (si.id, m.id)):
                    s.add(Inventory(
                        site_id=si.id,
                        material_id=m.id,
                        qty_on_hand=50.0,
                        reorder_point=10.0
                    ))
        # seed work orders
        if not s.exec(select(WorkOrder)).all():
            s.add_all([
                WorkOrder(
                    site_id=sites[0].id,
                    type="corrective",
                    status="new",
                    priority="high",
                    title="Авария дробилки",
                    description="Повышенный шум, возможен износ подшипника."
                ),
                WorkOrder(
                    site_id=sites[1].id,
                    type="preventive",
                    status="in_progress",
                    priority="normal",
                    title="Плановый осмотр конвейера"
                ),
                WorkOrder(
                    site_id=sites[0].id,
                    type="corrective",
                    status="done",
                    priority="normal",
                    title="Замена ремня привода"
                ),
            ])
        # seed plan + items
        if not s.exec(select(ProductionPlan)).all():
            p = ProductionPlan(site_id=sites[0].id, period="2025-11", status="published")
            s.add(p)
            s.commit()
            s.refresh(p)
            s.add_all([
                PlanItem(plan_id=p.id, product_name="Редуктор RX", quantity=120),
                PlanItem(plan_id=p.id, product_name="Вал 40Х", quantity=60),
            ])
        # seed suppliers & purchase orders
        if not s.exec(select(Supplier)).all():
            s.add_all([
                Supplier(name="ООО «МехСнаб»", contact="mechs@sample.local"),
                Supplier(name="АО «ТехМаркет»", contact="techm@sample.local"),
            ])
        s.commit()
        suppliers = s.exec(select(Supplier)).all()
        if suppliers and not s.exec(select(PurchaseOrder)).all():
            s.add(PurchaseOrder(
                supplier_id=suppliers[0].id,
                site_id=sites[0].id,
                status="in_progress",
                comment="Стартовый заказ под проект."
            ))
        # seed events
        if not s.exec(select(Event)).all():
            s.add_all([
                Event(type="auth_login", text="Первый вход в систему", severity="success"),
                Event(type="plan_published", text="Опубликован план производства 2025-11", severity="info"),
                Event(type="work_order", text="Создан ТОиР #1 (Площадка А)", severity="warning"),
            ])
        s.commit()


create_db_and_seed()

# ---- Auth (very simple cookie) ----
SESSIONS: Dict[str, int] = {}


class LoginPayload(BaseModel):
    login: str
    password: str


def current_user_cookie(session: Optional[str] = Cookie(default=None)):
    if not session or session not in SESSIONS:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return SESSIONS[session]


app = FastAPI(title="ЦПВП API", version=API_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
def index():
    return FileResponse(str(BASE_DIR / "frontend" / "index.html"))


@app.post(f"/api/{API_VERSION}/auth/login")
def login(payload: LoginPayload, response: Response):
    with Session(engine) as s:
        user = s.exec(select(User).where(User.login == payload.login)).first()
        if not user or user.password_hash != payload.password or user.blocked:
            raise HTTPException(status_code=401, detail="Неверные учетные данные")
        token = secrets.token_hex(16)
        SESSIONS[token] = user.id
        response.set_cookie("session", token, httponly=True, samesite="lax")
        # log event
        s.add(Event(type="auth_login", text=f"Вход: {user.login}", severity="success"))
        s.commit()
        return {"ok": True}


@app.post(f"/api/{API_VERSION}/auth/logout")
def logout(response: Response, session: Optional[str] = Cookie(default=None)):
    if session and session in SESSIONS:
        SESSIONS.pop(session, None)
    response.delete_cookie("session")
    return {"ok": True}


@app.get(f"/api/{API_VERSION}/auth/me")
def me(user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        u = s.get(User, user_id)
        roles = s.exec(
            select(Role).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == user_id)
        ).all()
        return {
            "id": u.id,
            "login": u.login,
            "email": u.email,
            "roles": [r.name for r in roles],
            "blocked": u.blocked
        }


# ---- Helpers ----
def paginate(q, page: int, page_size: int, s: Session):
    total = len(s.exec(q).all())
    items = s.exec(q.offset((page - 1) * page_size).limit(page_size)).all()
    return total, items


def log_event(session: Session, typ: str, text: str,
              severity: str = "info", meta: Optional[Dict[str, Any]] = None):
    ev = Event(type=typ, text=text, severity=severity,
               meta=str(meta) if meta else None)
    session.add(ev)
    session.commit()


def ensure_admin(user_id: int):
    with Session(engine) as s:
        q = select(Role.name).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == user_id)
        names = [r[0] for r in s.exec(q).all()]
        if "admin" not in names:
            raise HTTPException(status_code=403, detail="Только администратор")


# ---- Users & Roles CRUD ----
class UserOut(BaseModel):
    id: int
    login: str
    email: Optional[str]
    blocked: bool
    roles: List[str]


class UserCreate(BaseModel):
    login: str
    password: str
    email: Optional[str] = None
    roles: List[str] = []


class UserUpdate(BaseModel):
    email: Optional[str] = None
    blocked: Optional[bool] = None
    password: Optional[str] = None
    roles: Optional[List[str]] = None


class RoleCreate(BaseModel):
    name: str


class RoleUpdate(BaseModel):
    name: str


@app.get(f"/api/{API_VERSION}/users")
def list_users(user_id: int = Depends(current_user_cookie)):
    ensure_admin(user_id)
    with Session(engine) as s:
        users = s.exec(select(User)).all()
        out: List[UserOut] = []
        for u in users:
            rnames = [r[0] for r in s.exec(
                select(Role.name).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == u.id)
            ).all()]
            out.append(UserOut(id=u.id, login=u.login, email=u.email, blocked=u.blocked, roles=rnames))
        return {"results": [o.dict() for o in out]}


@app.post(f"/api/{API_VERSION}/users", status_code=201)
def create_user(payload: UserCreate, user_id: int = Depends(current_user_cookie)):
    ensure_admin(user_id)
    with Session(engine) as s:
        exists = s.exec(select(User).where(User.login == payload.login)).first()
        if exists:
            raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")
        u = User(login=payload.login, password_hash=payload.password, email=payload.email)
        s.add(u)
        s.commit()
        s.refresh(u)
        # привязка ролей
        for rname in payload.roles:
            r = s.exec(select(Role).where(Role.name == rname)).first()
            if not r:
                r = Role(name=rname)
                s.add(r)
                s.commit()
                s.refresh(r)
            s.add(UserRole(user_id=u.id, role_id=r.id))
        s.commit()
        log_event(s, "user_created", f"Создан пользователь {u.login}", "success", {"user_id": u.id})
        return {"id": u.id}


@app.put(f"/api/{API_VERSION}/users/{{uid}}", status_code=204)
def update_user(uid: int, payload: UserUpdate, user_id: int = Depends(current_user_cookie)):
    ensure_admin(user_id)
    with Session(engine) as s:
        u = s.get(User, uid)
        if not u:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if payload.email is not None:
            u.email = payload.email
        if payload.blocked is not None:
            u.blocked = payload.blocked
        if payload.password:
            u.password_hash = payload.password
        s.add(u)
        s.commit()
        # обновление ролей
        if payload.roles is not None:
            # удалить старые роли
            s.exec("DELETE FROM userrole WHERE user_id = :uid", {"uid": u.id})
            for rname in payload.roles:
                r = s.exec(select(Role).where(Role.name == rname)).first()
                if not r:
                    r = Role(name=rname)
                    s.add(r)
                    s.commit()
                    s.refresh(r)
                s.add(UserRole(user_id=u.id, role_id=r.id))
            s.commit()
        log_event(s, "user_updated", f"Обновлён пользователь {u.login}", "info", {"user_id": u.id})
        return Response(status_code=204)


@app.delete(f"/api/{API_VERSION}/users/{{uid}}", status_code=204)
def delete_user(uid: int, user_id: int = Depends(current_user_cookie)):
    ensure_admin(user_id)
    with Session(engine) as s:
        u = s.get(User, uid)
        if not u:
            return Response(status_code=204)
        s.exec("DELETE FROM userrole WHERE user_id = :uid", {"uid": uid})
        s.delete(u)
        s.commit()
        log_event(s, "user_deleted", f"Удалён пользователь #{uid}", "danger", {"user_id": uid})
        return Response(status_code=204)


@app.get(f"/api/{API_VERSION}/roles")
def list_roles(user_id: int = Depends(current_user_cookie)):
    ensure_admin(user_id)
    with Session(engine) as s:
        roles = s.exec(select(Role)).all()
        return {"results": [{"id": r.id, "name": r.name} for r in roles]}


@app.post(f"/api/{API_VERSION}/roles", status_code=201)
def create_role(payload: RoleCreate, user_id: int = Depends(current_user_cookie)):
    ensure_admin(user_id)
    with Session(engine) as s:
        exists = s.exec(select(Role).where(Role.name == payload.name)).first()
        if exists:
            raise HTTPException(status_code=400, detail="Такая роль уже существует")
        r = Role(name=payload.name)
        s.add(r)
        s.commit()
        s.refresh(r)
        log_event(s, "role_created", f"Создана роль {r.name}", "success", {"role_id": r.id})
        return {"id": r.id}


@app.put(f"/api/{API_VERSION}/roles/{{rid}}", status_code=204)
def update_role(rid: int, payload: RoleUpdate, user_id: int = Depends(current_user_cookie)):
    ensure_admin(user_id)
    with Session(engine) as s:
        r = s.get(Role, rid)
        if not r:
            raise HTTPException(status_code=404, detail="Роль не найдена")
        r.name = payload.name
        s.add(r)
        s.commit()
        log_event(s, "role_updated", f"Обновлена роль #{rid}", "info", {"role_id": rid})
        return Response(status_code=204)


@app.delete(f"/api/{API_VERSION}/roles/{{rid}}", status_code=204)
def delete_role(rid: int, user_id: int = Depends(current_user_cookie)):
    ensure_admin(user_id)
    with Session(engine) as s:
        r = s.get(Role, rid)
        if not r:
            return Response(status_code=204)
        s.exec("DELETE FROM userrole WHERE role_id = :rid", {"rid": rid})
        s.delete(r)
        s.commit()
        log_event(s, "role_deleted", f"Удалена роль #{rid}", "danger", {"role_id": rid})
        return Response(status_code=204)


# ---- Simple lists ----
@app.get(f"/api/{API_VERSION}/sites")
def list_sites(page: int = 1, page_size: int = 50, _: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        q = select(Site)
        total, items = paginate(q, page, page_size, s)
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "results": [{"id": i.id, "name": i.name, "region": i.region} for i in items]
        }


@app.get(f"/api/{API_VERSION}/equipment")
def list_equipment(
    page: int = 1,
    page_size: int = 100,
    site_id: Optional[int] = None,
    status: Optional[str] = None,
    _: int = Depends(current_user_cookie)
):
    with Session(engine) as s:
        q = select(Equipment)
        if site_id:
            q = q.where(Equipment.site_id == site_id)
        if status:
            q = q.where(Equipment.status == status)
        total, items = paginate(q, page, page_size, s)
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "results": [
                {
                    "id": e.id,
                    "site_id": e.site_id,
                    "equipment_type_id": e.equipment_type_id,
                    "code": e.code,
                    "name": e.name,
                    "status": e.status,
                    "commissioning_date": e.commissioning_date.isoformat()
                }
                for e in items
            ]
        }


@app.get(f"/api/{API_VERSION}/equipment-types")
def list_equipment_types(_: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        types = s.exec(select(EquipmentType)).all()
        return {"results": [{"id": t.id, "name": t.name} for t in types]}


@app.get(f"/api/{API_VERSION}/materials")
def list_materials(page: int = 1, page_size: int = 200, _: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        q = select(Material)
        total, items = paginate(q, page, page_size, s)
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "results": [
                {"id": m.id, "name": m.name, "unit": m.unit, "reject_percent": m.reject_percent}
                for m in items
            ]
        }


@app.get(f"/api/{API_VERSION}/sites/{{site_id}}/inventory")
def site_inventory(site_id: int, _: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        site = s.get(Site, site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        inv = s.exec(select(Inventory).where(Inventory.site_id == site_id)).all()
        items = []
        for i in inv:
            m = s.get(Material, i.material_id)
            items.append({
                "material_id": m.id,
                "material_name": m.name,
                "unit": m.unit,
                "qty_on_hand": i.qty_on_hand,
                "reorder_point": i.reorder_point
            })
        return {"site_id": site_id, "items": items}


@app.get(f"/api/{API_VERSION}/inventory")
def list_inventory(_: int = Depends(current_user_cookie)):
    """Общий список остатков (для /inventory из ТЗ)."""
    with Session(engine) as s:
        inv = s.exec(select(Inventory)).all()
        results = []
        for i in inv:
            m = s.get(Material, i.material_id)
            si = s.get(Site, i.site_id)
            results.append({
                "site_id": i.site_id,
                "site_name": si.name if si else "",
                "material_id": m.id,
                "material_name": m.name if m else "",
                "unit": m.unit if m else "",
                "qty_on_hand": i.qty_on_hand,
                "reorder_point": i.reorder_point,
            })
        return {"results": results}


# ---- CRUD basic ----
class SiteCreate(BaseModel):
    name: str
    region: str


class SiteUpdate(BaseModel):
    name: str
    region: str


@app.post(f"/api/{API_VERSION}/sites", status_code=201)
def create_site(payload: SiteCreate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        site = Site(name=payload.name, region=payload.region)
        s.add(site)
        s.commit()
        s.refresh(site)
        log_event(s, "site_created", f"Добавлена площадка {site.name}", "success", {"site_id": site.id})
        return {"id": site.id}


@app.put(f"/api/{API_VERSION}/sites/{{site_id}}", status_code=204)
def update_site(site_id: int, payload: SiteUpdate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        site = s.get(Site, site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Площадка не найдена")
        site.name = payload.name
        site.region = payload.region
        s.add(site)
        s.commit()
        log_event(s, "site_updated", f"Обновлена площадка #{site_id}", "info", {"site_id": site_id})
        return Response(status_code=204)


@app.delete(f"/api/{API_VERSION}/sites/{{site_id}}", status_code=204)
def delete_site(site_id: int, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        site = s.get(Site, site_id)
        if not site:
            return Response(status_code=204)
        s.delete(site)
        s.commit()
        log_event(s, "site_deleted", f"Удалена площадка #{site_id}", "danger", {"site_id": site_id})
        return Response(status_code=204)


class EquipmentCreate(BaseModel):
    site_id: int
    equipment_type_id: int
    code: str
    name: str
    status: str = "active"
    commissioning_date: date


class EquipmentUpdate(EquipmentCreate):
    pass


@app.post(f"/api/{API_VERSION}/equipment", status_code=201)
def create_equipment(payload: EquipmentCreate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        eq = Equipment(**payload.dict())
        s.add(eq)
        s.commit()
        s.refresh(eq)
        log_event(s, "equipment_created", f"Добавлено оборудование {eq.code}", "success", {"equipment_id": eq.id})
        return {"id": eq.id}


@app.put(f"/api/{API_VERSION}/equipment/{{equipment_id}}", status_code=204)
def update_equipment(equipment_id: int, payload: EquipmentUpdate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        eq = s.get(Equipment, equipment_id)
        if not eq:
            raise HTTPException(status_code=404, detail="Оборудование не найдено")
        for k, v in payload.dict().items():
            setattr(eq, k, v)
        s.add(eq)
        s.commit()
        log_event(s, "equipment_updated", f"Обновлено оборудование #{equipment_id}", "info", {"equipment_id": equipment_id})
        return Response(status_code=204)


@app.delete(f"/api/{API_VERSION}/equipment/{{equipment_id}}", status_code=204)
def delete_equipment(equipment_id: int, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        eq = s.get(Equipment, equipment_id)
        if not eq:
            return Response(status_code=204)
        s.delete(eq)
        s.commit()
        log_event(s, "equipment_deleted", f"Удалено оборудование #{equipment_id}", "danger", {"equipment_id": equipment_id})
        return Response(status_code=204)


class MaterialCreate(BaseModel):
    name: str
    unit: str
    description: Optional[str] = None
    reject_percent: Optional[float] = 0.0


class MaterialUpdate(MaterialCreate):
    pass


@app.post(f"/api/{API_VERSION}/materials", status_code=201)
def create_material(payload: MaterialCreate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        m = Material(**payload.dict())
        s.add(m)
        s.commit()
        s.refresh(m)
        log_event(s, "material_created", f"Добавлен материал {m.name}", "success", {"material_id": m.id})
        return {"id": m.id}


@app.put(f"/api/{API_VERSION}/materials/{{material_id}}", status_code=204)
def update_material(material_id: int, payload: MaterialUpdate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        m = s.get(Material, material_id)
        if not m:
            raise HTTPException(status_code=404, detail="Материал не найден")
        for k, v in payload.dict().items():
            setattr(m, k, v)
        s.add(m)
        s.commit()
        log_event(s, "material_updated", f"Обновлён материал #{material_id}", "info", {"material_id": material_id})
        return Response(status_code=204)


@app.delete(f"/api/{API_VERSION}/materials/{{material_id}}", status_code=204)
def delete_material(material_id: int, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        m = s.get(Material, material_id)
        if not m:
            return Response(status_code=204)
        s.delete(m)
        s.commit()
        log_event(s, "material_deleted", f"Удалён материал #{material_id}", "danger", {"material_id": material_id})
        return Response(status_code=204)


class InventoryUpdate(BaseModel):
    qty_on_hand: float
    reorder_point: float


@app.put(f"/api/{API_VERSION}/sites/{{site_id}}/inventory/{{material_id}}", status_code=204)
def update_inventory(site_id: int, material_id: int, payload: InventoryUpdate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        inv = s.get(Inventory, (site_id, material_id))
        if not inv:
            inv = Inventory(site_id=site_id, material_id=material_id)
        inv.qty_on_hand = payload.qty_on_hand
        inv.reorder_point = payload.reorder_point
        s.add(inv)
        s.commit()
        log_event(
            s,
            "inventory_updated",
            f"Обновлён запас по мат.#{material_id} @ site #{site_id}",
            "info",
            {"site_id": site_id, "material_id": material_id}
        )
        return Response(status_code=204)


# ---- Inventory moves (reserve/consume/add) ----
class InventoryMove(BaseModel):
    site_id: int
    material_id: int
    qty: float


@app.post(f"/api/{API_VERSION}/inventory/reserve", status_code=204)
def inventory_reserve(payload: InventoryMove, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        inv = s.get(Inventory, (payload.site_id, payload.material_id))
        if not inv:
            inv = Inventory(site_id=payload.site_id, material_id=payload.material_id)
        inv.qty_on_hand = max(0.0, inv.qty_on_hand - payload.qty)
        s.add(inv)
        s.commit()
        log_event(s, "inventory_reserve", f"Резерв материалов {payload.qty}", "info", payload.dict())
        return Response(status_code=204)


@app.post(f"/api/{API_VERSION}/inventory/consume", status_code=204)
def inventory_consume(payload: InventoryMove, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        inv = s.get(Inventory, (payload.site_id, payload.material_id))
        if not inv:
            inv = Inventory(site_id=payload.site_id, material_id=payload.material_id)
        inv.qty_on_hand = max(0.0, inv.qty_on_hand - payload.qty)
        s.add(inv)
        s.commit()
        log_event(s, "inventory_consume", f"Списание материалов {payload.qty}", "warning", payload.dict())
        return Response(status_code=204)


@app.post(f"/api/{API_VERSION}/inventory/add", status_code=204)
def inventory_add(payload: InventoryMove, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        inv = s.get(Inventory, (payload.site_id, payload.material_id))
        if not inv:
            inv = Inventory(site_id=payload.site_id, material_id=payload.material_id)
        inv.qty_on_hand = inv.qty_on_hand + payload.qty
        s.add(inv)
        s.commit()
        log_event(s, "inventory_add", f"Пополнение материалов {payload.qty}", "success", payload.dict())
        return Response(status_code=204)


# ---- Work Orders ----
class WorkOrderBase(BaseModel):
    site_id: int
    type: str
    status: str = "new"
    priority: str = "normal"
    title: str = "Заявка ТОиР"
    description: Optional[str] = None
    equipment_id: Optional[int] = None
    planned_date: Optional[date] = None
    assigned_team: Optional[str] = None


class WorkOrderCreate(WorkOrderBase):
    pass


class WorkOrderUpdate(BaseModel):
    site_id: Optional[int] = None
    type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    equipment_id: Optional[int] = None
    planned_date: Optional[date] = None
    assigned_team: Optional[str] = None


class WorkOrderAssign(BaseModel):
    assigned_team: str


class WorkOrderStatus(BaseModel):
    status: str


class WorkOrderMaterialItem(BaseModel):
    material_id: int
    qty_planned: float = 0.0
    qty_fact: float = 0.0


class WorkOrderMaterialsPayload(BaseModel):
    items: List[WorkOrderMaterialItem]


class WorkOrderCommentPayload(BaseModel):
    text: str


@app.get(f"/api/{API_VERSION}/workorders")
def list_workorders(
    site_id: Optional[int] = None,
    status: Optional[str] = None,
    _: int = Depends(current_user_cookie)
):
    with Session(engine) as s:
        q = select(WorkOrder)
        if site_id:
            q = q.where(WorkOrder.site_id == site_id)
        if status:
            q = q.where(WorkOrder.status == status)
        items = s.exec(q.order_by(WorkOrder.created_at.desc())).all()
        return {"results": [
            {
                "id": w.id,
                "site_id": w.site_id,
                "type": w.type,
                "status": w.status,
                "priority": w.priority,
                "title": w.title,
                "description": w.description,
                "equipment_id": w.equipment_id,
                "planned_date": w.planned_date.isoformat() if w.planned_date else None,
                "assigned_team": w.assigned_team,
                "created_at": w.created_at.isoformat()
            }
            for w in items
        ]}


@app.post(f"/api/{API_VERSION}/workorders", status_code=201)
def create_workorder(payload: WorkOrderCreate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        w = WorkOrder(**payload.dict())
        s.add(w)
        s.commit()
        s.refresh(w)
        log_event(s, "work_order", f"Создана заявка ТОиР #{w.id}", "warning", {"work_order_id": w.id})
        return {"id": w.id}


@app.get(f"/api/{API_VERSION}/workorders/{{wid}}")
def get_workorder(wid: int, _: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        w = s.get(WorkOrder, wid)
        if not w:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        mats = s.exec(select(WorkOrderMaterial).where(WorkOrderMaterial.work_order_id == wid)).all()
        comments = s.exec(
            select(WorkOrderComment)
            .where(WorkOrderComment.work_order_id == wid)
            .order_by(WorkOrderComment.created_at)
        ).all()
        return {
            "id": w.id,
            "site_id": w.site_id,
            "type": w.type,
            "status": w.status,
            "priority": w.priority,
            "title": w.title,
            "description": w.description,
            "equipment_id": w.equipment_id,
            "planned_date": w.planned_date.isoformat() if w.planned_date else None,
            "assigned_team": w.assigned_team,
            "created_at": w.created_at.isoformat(),
            "materials": [
                {"material_id": m.material_id, "qty_planned": m.qty_planned, "qty_fact": m.qty_fact}
                for m in mats
            ],
            "comments": [
                {"author_id": c.author_id, "text": c.text, "created_at": c.created_at.isoformat()}
                for c in comments
            ],
        }


@app.put(f"/api/{API_VERSION}/workorders/{{wid}}", status_code=204)
def update_workorder(wid: int, payload: WorkOrderUpdate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        w = s.get(WorkOrder, wid)
        if not w:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        for k, v in payload.dict(exclude_none=True).items():
            setattr(w, k, v)
        s.add(w)
        s.commit()
        log_event(s, "work_order_updated", f"Обновлена заявка ТОиР #{wid}", "info", {"work_order_id": wid})
        return Response(status_code=204)


@app.delete(f"/api/{API_VERSION}/workorders/{{wid}}", status_code=204)
def delete_workorder(wid: int, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        w = s.get(WorkOrder, wid)
        if not w:
            return Response(status_code=204)
        s.delete(w)
        s.commit()
        log_event(s, "work_order_deleted", f"Удалена заявка ТОиР #{wid}", "danger", {"work_order_id": wid})
        return Response(status_code=204)


@app.post(f"/api/{API_VERSION}/workorders/{{wid}}/assign", status_code=204)
def assign_workorder(wid: int, payload: WorkOrderAssign, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        w = s.get(WorkOrder, wid)
        if not w:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        w.assigned_team = payload.assigned_team
        s.add(w)
        s.commit()
        log_event(
            s,
            "work_order_assign",
            f"Назначена бригада для ТОиР #{wid}",
            "info",
            {"work_order_id": wid, "team": payload.assigned_team}
        )
        return Response(status_code=204)


@app.post(f"/api/{API_VERSION}/workorders/{{wid}}/status", status_code=204)
def status_workorder(wid: int, payload: WorkOrderStatus, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        w = s.get(WorkOrder, wid)
        if not w:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        w.status = payload.status
        s.add(w)
        s.commit()
        sev = "success" if payload.status in ("done", "closed") else "info"
        log_event(
            s,
            "work_order_status",
            f"Статус ТОиР #{wid} -> {payload.status}",
            sev,
            {"work_order_id": wid, "status": payload.status}
        )
        return Response(status_code=204)


@app.post(f"/api/{API_VERSION}/workorders/{{wid}}/materials", status_code=204)
def workorder_materials(wid: int, payload: WorkOrderMaterialsPayload, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        w = s.get(WorkOrder, wid)
        if not w:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        # очистить старые
        s.exec("DELETE FROM workordermaterial WHERE work_order_id = :wid", {"wid": wid})
        for item in payload.items:
            m = WorkOrderMaterial(
                work_order_id=wid,
                material_id=item.material_id,
                qty_planned=item.qty_planned,
                qty_fact=item.qty_fact
            )
            s.add(m)
        s.commit()
        log_event(s, "work_order_materials", f"Материалы по ТОиР #{wid} обновлены", "info", {"work_order_id": wid})
        return Response(status_code=204)


@app.post(f"/api/{API_VERSION}/workorders/{{wid}}/comment", status_code=201)
def workorder_comment(wid: int, payload: WorkOrderCommentPayload, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        w = s.get(WorkOrder, wid)
        if not w:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        c = WorkOrderComment(work_order_id=wid, author_id=user_id, text=payload.text)
        s.add(c)
        s.commit()
        s.refresh(c)
        log_event(s, "work_order_comment", f"Комментарий к ТОиР #{wid}", "info", {"work_order_id": wid})
        return {"id": c.id}


# ---- Supply (suppliers & purchase_orders) ----
class SupplierCreate(BaseModel):
    name: str
    contact: Optional[str] = None


class SupplierUpdate(SupplierCreate):
    pass


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    site_id: int
    comment: Optional[str] = None


class PurchaseOrderUpdate(BaseModel):
    status: Optional[str] = None
    comment: Optional[str] = None


@app.get(f"/api/{API_VERSION}/suppliers")
def list_suppliers(_: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        rows = s.exec(select(Supplier)).all()
        return {"results": [{"id": r.id, "name": r.name, "contact": r.contact} for r in rows]}


@app.post(f"/api/{API_VERSION}/suppliers", status_code=201)
def create_supplier(payload: SupplierCreate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        sup = Supplier(**payload.dict())
        s.add(sup)
        s.commit()
        s.refresh(sup)
        log_event(s, "supplier_created", f"Добавлен поставщик {sup.name}", "success", {"supplier_id": sup.id})
        return {"id": sup.id}


@app.put(f"/api/{API_VERSION}/suppliers/{{sid}}", status_code=204)
def update_supplier(sid: int, payload: SupplierUpdate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        sup = s.get(Supplier, sid)
        if not sup:
            raise HTTPException(status_code=404, detail="Поставщик не найден")
        sup.name = payload.name
        sup.contact = payload.contact
        s.add(sup)
        s.commit()
        log_event(s, "supplier_updated", f"Обновлён поставщик #{sid}", "info", {"supplier_id": sid})
        return Response(status_code=204)


@app.get(f"/api/{API_VERSION}/purchase_orders")
def list_purchase_orders(_: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        pos = s.exec(select(PurchaseOrder)).all()
        out = []
        for p in pos:
            sup = s.get(Supplier, p.supplier_id)
            si = s.get(Site, p.site_id)
            out.append({
                "id": p.id,
                "supplier_id": p.supplier_id,
                "supplier_name": sup.name if sup else "",
                "site_id": p.site_id,
                "site_name": si.name if si else "",
                "status": p.status,
                "comment": p.comment,
                "created_at": p.created_at.isoformat()
            })
        return {"results": out}


@app.post(f"/api/{API_VERSION}/purchase_orders", status_code=201)
def create_purchase_order(payload: PurchaseOrderCreate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        po = PurchaseOrder(**payload.dict())
        s.add(po)
        s.commit()
        s.refresh(po)
        log_event(s, "po_created", f"Создан заказ поставщику #{po.id}", "info", {"po_id": po.id})
        return {"id": po.id}


@app.put(f"/api/{API_VERSION}/purchase_orders/{{pid}}", status_code=204)
def update_purchase_order(pid: int, payload: PurchaseOrderUpdate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        po = s.get(PurchaseOrder, pid)
        if not po:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        if payload.status is not None:
            po.status = payload.status
        if payload.comment is not None:
            po.comment = payload.comment
        s.add(po)
        s.commit()
        log_event(s, "po_updated", f"Обновлён заказ поставщику #{pid}", "info", {"po_id": pid})
        return Response(status_code=204)


# ---- Plans ----
class PlanCreate(BaseModel):
    site_id: int
    period: str
    status: str = "draft"


class PlanItemCreate(BaseModel):
    product_name: str
    quantity: int


@app.get(f"/api/{API_VERSION}/plans")
def list_plans(site_id: Optional[int] = None, _: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        q = select(ProductionPlan)
        if site_id:
            q = q.where(ProductionPlan.site_id == site_id)
        plans = s.exec(q).all()
        out = []
        for p in plans:
            si = s.get(Site, p.site_id)
            out.append({
                "id": p.id,
                "site_id": p.site_id,
                "site_name": si.name if si else "",
                "period": p.period,
                "status": p.status
            })
        return {"results": out}


@app.post(f"/api/{API_VERSION}/plans", status_code=201)
def create_plan(payload: PlanCreate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        p = ProductionPlan(**payload.dict())
        s.add(p)
        s.commit()
        s.refresh(p)
        log_event(s, "plan_created", f"Создан план {p.period} @ site {p.site_id}", "info", {"plan_id": p.id})
        return {"id": p.id}


@app.get(f"/api/{API_VERSION}/plans/{{pid}}")
def get_plan(pid: int, _: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        p = s.get(ProductionPlan, pid)
        if not p:
            raise HTTPException(status_code=404, detail="План не найден")
        si = s.get(Site, p.site_id)
        items = s.exec(select(PlanItem).where(PlanItem.plan_id == pid)).all()
        return {
            "id": p.id,
            "site_id": p.site_id,
            "site_name": si.name if si else "",
            "period": p.period,
            "status": p.status,
            "items": [{"id": i.id, "product_name": i.product_name, "quantity": i.quantity} for i in items]
        }


@app.post(f"/api/{API_VERSION}/plans/{{pid}}/items", status_code=201)
def add_plan_item(pid: int, payload: PlanItemCreate, user_id: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        p = s.get(ProductionPlan, pid)
        if not p:
            raise HTTPException(status_code=404, detail="План не найден")
        item = PlanItem(plan_id=pid, product_name=payload.product_name, quantity=payload.quantity)
        s.add(item)
        s.commit()
        s.refresh(item)
        log_event(s, "plan_item", f"Добавлена позиция в план #{pid}", "info",
                  {"plan_id": pid, "item_id": item.id})
        return {"id": item.id}


# ---- Events & Reports ----
@app.get(f"/api/{API_VERSION}/events")
def get_events(limit: int = 40, _: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        ev = s.exec(select(Event).order_by(Event.created_at.desc()).limit(limit)).all()
        return {"results": [
            {
                "id": e.id,
                "type": e.type,
                "text": e.text,
                "severity": e.severity,
                "created_at": e.created_at.isoformat()
            }
            for e in ev
        ]}


@app.get(f"/api/{API_VERSION}/reports/work_orders_by_status")
def rpt_wo_status(_: int = Depends(current_user_cookie)):
    from collections import Counter
    with Session(engine) as s:
        rows = s.exec(select(WorkOrder.status)).all()
        c = Counter([r[0] for r in rows])
        return {"results": [{"status": k, "count": v} for k, v in c.items()]}


@app.get(f"/api/{API_VERSION}/reports/inventory_breakdown")
def rpt_inv(_: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        inv = s.exec(select(Inventory)).all()
        low = sum(1 for i in inv if i.qty_on_hand < i.reorder_point)
        ok = len(inv) - low
        return {"ok": ok, "low": low}


@app.get(f"/api/{API_VERSION}/reports/top_products")
def rpt_top_products(_: int = Depends(current_user_cookie)):
    with Session(engine) as s:
        items = s.exec(select(PlanItem)).all()
        items = sorted(items, key=lambda x: x.quantity, reverse=True)[:8]
        return {"results": [{"product_name": i.product_name, "quantity": i.quantity} for i in items]}


# ---- Analytics (/analytics/* из ТЗ) ----
@app.get(f"/api/{API_VERSION}/analytics/dashboard")
def analytics_dashboard(_: int = Depends(current_user_cookie)):
    from collections import Counter
    with Session(engine) as s:
        wo = s.exec(select(WorkOrder)).all()
        c = Counter([w.status for w in wo])
        inv = s.exec(select(Inventory)).all()
        low = sum(1 for i in inv if i.qty_on_hand < i.reorder_point)
        ok = len(inv) - low
        plans = s.exec(select(ProductionPlan)).all()
        items = s.exec(select(PlanItem)).all()
        top = sorted(items, key=lambda x: x.quantity, reverse=True)[:5]
        return {
            "work_orders_total": len(wo),
            "work_orders_by_status": [{"status": k, "count": v} for k, v in c.items()],
            "inventory": {"ok": ok, "low": low},
            "plans_total": len(plans),
            "top_products": [{"product_name": i.product_name, "quantity": i.quantity} for i in top],
        }


@app.get(f"/api/{API_VERSION}/analytics/kpi")
def analytics_kpi(_: int = Depends(current_user_cookie)):
    from collections import defaultdict
    with Session(engine) as s:
        sites = s.exec(select(Site)).all()
        wo = s.exec(select(WorkOrder)).all()
        by_site: Dict[int, List[WorkOrder]] = defaultdict(list)
        for w in wo:
            by_site[w.site_id].append(w)
        site_rows = []
        for si in sites:
            ws = by_site.get(si.id, [])
            total = len(ws)
            done = sum(1 for w in ws if w.status in ("done", "closed"))
            high = sum(1 for w in ws if w.priority == "high")
            site_rows.append({
                "site_id": si.id,
                "site_name": si.name,
                "wo_total": total,
                "wo_done": done,
                "wo_high": high,
            })
        # KPI сотрудников пока пустой заглушкой
        return {"sites": site_rows, "staff": []}
