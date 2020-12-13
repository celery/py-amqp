from typing import Any, AnyStr, Mapping, Optional, Union

SSLArg = Union[Mapping[AnyStr, Any], bool]
MaybeDict = Optional[Mapping[AnyStr, Any]]
Timeout = Optional[float]