from datetime import datetime

from pydantic import BaseModel, Field

from app.models.models import Role, WorkflowState


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    must_reset_password: bool


class LoginInput(BaseModel):
    username: str
    password: str


class PasswordResetInput(BaseModel):
    new_password: str = Field(min_length=12)


class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    must_reset_password: bool

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=12)
    role: Role


class ChartCreate(BaseModel):
    client_name: str
    level_of_care: str
    primary_clinician: str
    notes: str = ''


class ChartOut(BaseModel):
    id: int
    client_name: str
    level_of_care: str
    primary_clinician: str
    counselor_id: int
    state: WorkflowState
    notes: str

    class Config:
        from_attributes = True


class TransitionInput(BaseModel):
    to_state: WorkflowState
    comment: str = ''


class AuditLogOut(BaseModel):
    timestamp_utc: datetime
    actor_username: str | None
    actor_role: str | None
    source_ip: str | None
    request_id: str
    action: str
    target_entity: str | None
    details: str
    outcome_status: str
    severity: str
