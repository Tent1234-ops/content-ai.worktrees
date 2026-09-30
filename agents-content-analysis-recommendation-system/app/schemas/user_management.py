from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    username: str = Field(min_length=3, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    role: Literal["admin", "user"] = "user"

    @field_validator("email")
    @classmethod
    def email_format(cls, value: str) -> str:
        value = value.lower()
        if value.count("@") != 1 or "." not in value.split("@")[-1] or any(c.isspace() for c in value):
            raise ValueError("Invalid email format")
        return value


class CreateAccount(AccountFields):
    # Preserve password whitespace, matching normal account registration.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username", "email", mode="before")
    @classmethod
    def trim_identity(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class AccountRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")


class UpdateAccount(AccountFields, AccountRevision):
    is_active: bool = Field(strict=True)


class DeleteAccount(AccountRevision):
    confirmation: str = Field(min_length=3, max_length=100)
