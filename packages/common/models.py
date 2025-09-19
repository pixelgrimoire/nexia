from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON as SAJSON

Base = declarative_base()

# Use a portable JSON column for cross-dialect compatibility in tests/dev.
JSONType = SAJSON

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    plan = Column(String, default="starter")
    billing_status = Column(String, default="trial")

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    email = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)
    status = Column(String, default="active")
    password_hash = Column(String)
    created_at = Column(DateTime)

class Channel(Base):
    __tablename__ = "channels"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    type = Column(String)
    mode = Column(String)
    status = Column(String)
    credentials = Column(JSONType)
    phone_number = Column(String)

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    wa_id = Column(String)
    phone = Column(String)
    name = Column(String)
    attributes = Column(JSONType, default=dict)
    # Use JSON array on SQLite; ARRAY(String) on Postgres isn't essential for tests
    tags = Column(JSONType, default=list)
    consent = Column(String)
    locale = Column(String)
    timezone = Column(String)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    contact_id = Column(ForeignKey("contacts.id"))
    channel_id = Column(ForeignKey("channels.id"))
    state = Column(String)
    assignee = Column(String)
    last_activity_at = Column(DateTime)

class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True)
    conversation_id = Column(ForeignKey("conversations.id"))
    direction = Column(String)  # in|out
    type = Column(String)       # text|media|template
    content = Column(JSONType)
    template_id = Column(String, nullable=True)
    status = Column(String)     # delivered|read|failed
    meta = Column(JSONType)
    client_id = Column(String)
    created_at = Column(DateTime)

class Template(Base):
    __tablename__ = "templates"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    name = Column(String)
    language = Column(String)
    category = Column(String)
    body = Column(Text)
    variables = Column(JSONType)
    status = Column(String)

class Flow(Base):
    __tablename__ = "flows"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    name = Column(String)
    version = Column(Integer)
    graph = Column(JSONType)
    status = Column(String)
    created_by = Column(String)
# Modelos comunes

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(String, primary_key=True)
    user_id = Column(ForeignKey("users.id"))
    token = Column(String)  # stored as opaque string (consider hashing in prod)
    expires_at = Column(DateTime)
    revoked = Column(String, default="false")


class FlowRun(Base):
    __tablename__ = "flow_runs"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    flow_id = Column(ForeignKey("flows.id"))
    status = Column(String)  # running|completed|failed
    last_step = Column(String)  # path/key of last executed step
    context = Column(JSONType)  # execution context/scratch
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class Note(Base):
    __tablename__ = "notes"
    id = Column(String, primary_key=True)
    conversation_id = Column(ForeignKey("conversations.id"))
    author = Column(String)  # user id or email
    body = Column(Text)
    created_at = Column(DateTime)


class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(String, primary_key=True)
    conversation_id = Column(ForeignKey("conversations.id"))
    url = Column(Text)
    filename = Column(String)
    uploaded_by = Column(String)
    created_at = Column(DateTime)
    storage_key = Column(String)  # optional object key when stored in S3/MinIO


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    actor = Column(String)          # email or user id
    action = Column(String)         # e.g., channel.created, flow.updated
    entity_type = Column(String)    # channel|flow|template|conversation|message|note|attachment|webhook
    entity_id = Column(String)      # id of the entity when applicable
    data = Column(JSONType)         # small payload snapshot
    created_at = Column(DateTime)


class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    name = Column(String, nullable=False)
    created_at = Column(DateTime)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    id = Column(String, primary_key=True)
    workspace_id = Column(ForeignKey("workspaces.id"))
    user_id = Column(ForeignKey("users.id"))
    role = Column(String, nullable=False)
    created_at = Column(DateTime)

