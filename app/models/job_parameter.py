from app.extensions import db
from app.models.parameter import VALUE_TYPES, ParameterMixin

__all__ = ["JobParameter", "VALUE_TYPES"]


class JobParameter(ParameterMixin, db.Model):
    """A key/value input for a JobDefinition's script (e.g. username, password,
    or non-secret config like a URL or timeout). See ParameterMixin for how
    secret vs. non-secret values are stored.
    """

    __tablename__ = "job_parameters"
    __table_args__ = (
        db.UniqueConstraint("job_definition_id", "key", name="uq_job_parameter_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    job_definition_id = db.Column(
        db.Integer,
        db.ForeignKey("job_definitions.id"),
        nullable=False,
        index=True,
    )

    job_definition = db.relationship("JobDefinition", back_populates="parameters")

    def __repr__(self) -> str:
        return f"<JobParameter {self.id} key={self.key!r} secret={self.is_secret}>"
