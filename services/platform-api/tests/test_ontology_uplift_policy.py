from app.algorithms.ontology_uplift_policy import Action, fit_and_optimize, synthetic_history


def test_policy_rejects_semantically_invalid_actions_before_scoring():
    history, actions = synthetic_history(seed=3, n=120)
    actions += [
        Action("pending", "c-0", "App", "P", 100, 1, 0.99, "pending"),
        Action("weak-evidence", "c-1", "App", "P", 100, 1, 0.2),
    ]
    result = fit_and_optimize(history, actions, budget=10, channel_caps={"App": 10, "SMS": 10})
    rejected = dict(result.rejected)
    assert rejected["pending"] == "ontology_gate:pending"
    assert rejected["weak-evidence"] == "evidence_below_floor"


def test_policy_respects_budget_channel_and_frequency_constraints():
    history, actions = synthetic_history(seed=4, n=200)
    result = fit_and_optimize(history, actions, budget=8, channel_caps={"App": 2, "SMS": 1, "WeChat": 1}, max_per_frequency_group=1)
    assert sum(x.action.contact_cost_yuan for x in result.selected) <= 8 + 1e-9
    assert sum(x.action.channel == "App" for x in result.selected) <= 2
    assert sum(x.action.channel == "SMS" for x in result.selected) <= 1
    assert sum(x.action.channel == "WeChat" for x in result.selected) <= 1
    groups = [x.action.frequency_group for x in result.selected]
    assert len(groups) == len(set(groups))


def test_policy_is_reproducible_for_same_snapshot_and_history():
    history, actions = synthetic_history(seed=8, n=200)
    first = fit_and_optimize(history, actions, budget=8, channel_caps={"App": 10, "SMS": 10, "WeChat": 10}, max_per_frequency_group=2)
    second = fit_and_optimize(history, actions, budget=8, channel_caps={"App": 10, "SMS": 10, "WeChat": 10}, max_per_frequency_group=2)
    assert [x.action.action_id for x in first.selected] == [x.action.action_id for x in second.selected]
    assert first.objective_value == second.objective_value
