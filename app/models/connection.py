from app.extensions import db
from app.models.parameter import ParameterMixin


class Connection(db.Model):
    """A reusable, named bundle of credentials/config attached to jobs.

    A job attaches one or more connections; their parameters are injected into
    the job's environment at launch. A connection flagged `is_mfa` is instead
    consumed server-side by the MFA provider (its secrets are never injected) —
    if a job has an attached MFA connection, that's what the MFA logic uses.
    """

    __tablename__ = "connections"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, index=True, nullable=False)
    # When true, this connection supplies email-MFA codes (its params:
    # tenant_id/client_id/client_secret/mailbox) and is used by the OTP provider
    # rather than injected into the job environment.
    is_mfa = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # Shared connections (config common to all clients) attach to every child of
    # a fan-out batch. Non-shared, non-MFA connections are the per-client
    # credentials the job fans out over (one child run each).
    is_shared = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    description = db.Column(db.Text, nullable=False, default="", server_default="")

    parameters = db.relationship(
        "ConnectionParameter",
        back_populates="connection",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Connection {self.id} name={self.name!r} is_mfa={self.is_mfa}>"


class ConnectionParameter(ParameterMixin, db.Model):
    """A key/value field belonging to a Connection (same secret/typed storage
    as JobParameter — see ParameterMixin)."""

    __tablename__ = "connection_parameters"
    __table_args__ = (
        db.UniqueConstraint("connection_id", "key", name="uq_connection_parameter_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    connection_id = db.Column(
        db.Integer,
        db.ForeignKey("connections.id"),
        nullable=False,
        index=True,
    )

    connection = db.relationship("Connection", back_populates="parameters")

    def __repr__(self) -> str:
        return f"<ConnectionParameter {self.id} key={self.key!r} secret={self.is_secret}>"


class JobDefinitionConnection(db.Model):
    """A connection attached to a job definition (its default set). Overridable
    per run (see JobRunConnection). Unique per (job, connection)."""

    __tablename__ = "job_definition_connections"
    __table_args__ = (
        db.UniqueConstraint("job_definition_id", "connection_id", name="uq_jobdef_conn"),
    )

    id = db.Column(db.Integer, primary_key=True)
    job_definition_id = db.Column(
        db.Integer, db.ForeignKey("job_definitions.id"), nullable=False, index=True
    )
    connection_id = db.Column(
        db.Integer, db.ForeignKey("connections.id"), nullable=False
    )

    job_definition = db.relationship("JobDefinition", back_populates="connection_bindings")
    connection = db.relationship("Connection")


class JobRunConnection(db.Model):
    """Per-run snapshot of which connections were attached — the definition
    defaults, possibly overridden at launch. The launcher and OTP provider read
    these (not the definition), so overrides and history are accurate."""

    __tablename__ = "job_run_connections"

    id = db.Column(db.Integer, primary_key=True)
    job_run_id = db.Column(
        db.Integer, db.ForeignKey("job_runs.id"), nullable=False, index=True
    )
    connection_id = db.Column(
        db.Integer, db.ForeignKey("connections.id"), nullable=False
    )

    job_run = db.relationship("JobRun", back_populates="connections")
    connection = db.relationship("Connection")
