from .schemas import Manual, User


READABLE_CATEGORIES_FOR_NAILIST = {"接客", "施術", "衛生管理", "予約"}


def can_read_manual(user: User, manual: Manual) -> bool:
    """RBACとABACを合わせて、文書を読めるか判定する。

    RBACはrole、つまり管理者・マネージャー・一般ネイリストの役割で基本権限を決める。
    ABACはorg_type、branch_id、visibility、statusなどの属性で追加条件を決める。
    RAGではこの判定を検索前後に必ず使い、権限外チャンクをLLMへ渡さない。
    """
    if user.role == "admin":
        return True

    if manual.status != "published":
        return can_edit_manual(user, manual)

    if manual.visibility == "admin_only":
        return False

    if user.role == "manager":
        if manual.visibility == "company":
            return True
        if manual.visibility == "manager_only":
            return True
        if manual.visibility == "headquarters":
            return user.org_type == "headquarters"
        if manual.visibility == "branch":
            return user.org_type == "branch" and user.branch_id == manual.branch_id
        return False

    if user.role == "nailist":
        if manual.visibility == "company" and manual.category in READABLE_CATEGORIES_FOR_NAILIST:
            return True
        if manual.visibility == "branch":
            return (
                user.org_type == "branch"
                and user.branch_id == manual.branch_id
                and manual.category in READABLE_CATEGORIES_FOR_NAILIST
            )
        return False

    return False


def can_edit_manual(user: User, manual: Manual | None = None) -> bool:
    """マニュアル編集権限を判定する。

    管理者は全件編集できる。マネージャーは自分の拠点に関係する文書だけ編集できる。
    一般ネイリストは閲覧と検索のみで、編集はできない。
    """
    if user.role == "admin":
        return True
    if user.role != "manager":
        return False
    if manual is None:
        return True
    if manual.visibility in {"company", "manager_only"}:
        return True
    if manual.visibility == "headquarters":
        return user.org_type == "headquarters"
    if manual.visibility == "branch":
        return user.org_type == "branch" and user.branch_id == manual.branch_id
    return False


def can_view_audit_log(requester: User, target_user: User | None = None) -> bool:
    if requester.role == "admin":
        return True
    if requester.role == "manager" and target_user is not None:
        return requester.branch_id is not None and requester.branch_id == target_user.branch_id
    return False

