"""
修复 langchain_community Tongyi：DashScope 非 200/400/401 时用 HTTPError(response=dashscope_resp)，
会触发 KeyError: 'request'，掩盖真实 API 错误（如额度用尽）。

在首次使用 ChatTongyi 之前调用 apply_patch()；已对 chat_models.tongyi 内已绑定的 check_response 同步替换。
"""

from __future__ import annotations

_applied = False


def apply_patch() -> None:
    global _applied
    if _applied:
        return

    def check_response_safe(resp):  # type: ignore[no-untyped-def]
        if resp["status_code"] == 200:
            return resp
        if resp["status_code"] in (400, 401):
            raise ValueError(
                f"request_id: {resp.get('request_id')} \n "
                f"status_code: {resp['status_code']} \n "
                f"code: {resp.get('code')} \n message: {resp.get('message')}"
            )
        raise RuntimeError(
            "DashScope API 错误\n"
            f"  status_code: {resp.get('status_code')}\n"
            f"  code: {resp.get('code')}\n"
            f"  message: {resp.get('message')}\n"
            f"  request_id: {resp.get('request_id')}"
        )

    from langchain_community.llms import tongyi as tongyi_llm

    tongyi_llm.check_response = check_response_safe
    try:
        from langchain_community.chat_models import tongyi as chat_tongyi

        chat_tongyi.check_response = check_response_safe
    except ImportError:
        pass
    _applied = True
