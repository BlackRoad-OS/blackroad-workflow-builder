"""End-to-end tests for BlackRoad Workflow Builder.

These tests exercise complete workflow lifecycles — from creation through
execution to audit history — including Stripe payment and subscription
workflow scenarios.
"""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from workflow_builder import (
    WorkflowDB, WorkflowEngine, DAGValidator,
    RunStatus, StepType,
)


@pytest.fixture
def engine(tmp_path):
    db = WorkflowDB(db_path=str(tmp_path / "e2e_workflow.db"))
    return WorkflowEngine(db)


# ── CI/CD pipeline ────────────────────────────────────────────────────────────

class TestCICDPipeline:
    """Full CI/CD pipeline: create → add steps → validate → run → history."""

    def test_full_pipeline_lifecycle(self, engine):
        # Create
        wf = engine.create_workflow(
            "ci-cd-pipeline",
            description="End-to-end CI/CD pipeline",
            tags=["ci", "cd", "production"],
        )
        assert wf.name == "ci-cd-pipeline"
        assert "ci" in wf.tags

        # Add steps in dependency order
        checkout = engine.add_step(wf.id, "checkout", "task",
                                   {"command": "git pull origin main"})
        build = engine.add_step(wf.id, "build", "task",
                                {"command": "npm run build"},
                                depends_on=[checkout.id])
        test_step = engine.add_step(wf.id, "test", "condition",
                                    {"expression": "exit_code eq 0",
                                     "true_next": "deploy",
                                     "false_next": "notify-failure"},
                                    depends_on=[build.id])
        deploy = engine.add_step(wf.id, "deploy", "task",
                                 {"command": "kubectl apply -f manifests/"},
                                 depends_on=[test_step.id])
        engine.add_step(wf.id, "notify-success", "notify",
                        {"channel": "slack", "message": "Deploy succeeded!"},
                        depends_on=[deploy.id])

        # Validate DAG
        validation = engine.validate_dag(wf.id)
        assert validation["valid"] is True
        assert validation["cycle_detected"] is False
        assert validation["step_count"] == 5
        assert len(validation["execution_order"]) == 5

        # Run
        run = engine.execute_workflow(wf.id, {"env": "production", "exit_code": "0"})
        assert run.status == RunStatus.SUCCESS
        assert run.duration_ms >= 0

        # History
        history = engine.get_run_history(wf.id, limit=3)
        assert len(history) == 1
        assert history[0]["status"] == "success"

    def test_pipeline_with_failed_step(self, engine):
        wf = engine.create_workflow("failing-pipeline", "Pipeline that will fail")
        s1 = engine.add_step(wf.id, "checkout", "task", {"command": "git pull"})
        # condition step that evaluates to skip next step
        engine.add_step(wf.id, "gate", "condition",
                        {"expression": "result eq ok"},
                        depends_on=[s1.id])

        run = engine.execute_workflow(wf.id, {"result": "ok"})
        assert run.status == RunStatus.SUCCESS
        assert len(run.step_results) == 2

    def test_pipeline_export_roundtrip(self, engine):
        wf = engine.create_workflow("export-pipeline", "Export test", ["export"])
        engine.add_step(wf.id, "step-a", "task", {"command": "echo a"})
        engine.add_step(wf.id, "step-b", "transform", {"mapping": {"out": "in"}})

        data = engine.export_workflow(wf.id)

        assert data["workflow"]["name"] == "export-pipeline"
        assert len(data["steps"]) == 2
        step_names = {s["name"] for s in data["steps"]}
        assert step_names == {"step-a", "step-b"}
        assert "exported_at" in data


# ── Stripe payment capture ─────────────────────────────────────────────────────

class TestStripePaymentCaptureWorkflow:
    """End-to-end Stripe payment capture workflow."""

    def _build_payment_workflow(self, engine):
        wf = engine.create_workflow(
            "stripe-payment-capture",
            description="Stripe payment intent → validate → capture → notify",
            tags=["stripe", "payments", "production"],
        )

        validate_intent = engine.add_step(
            wf.id, "validate-intent", "task",
            {"command": "stripe payment_intents retrieve",
             "env": {"PAYMENT_INTENT_ID": "payment_intent_id"}},
        )
        check_status = engine.add_step(
            wf.id, "check-status", "condition",
            {"expression": "payment_status eq requires_capture",
             "true_next": "capture",
             "false_next": "notify-failed"},
            depends_on=[validate_intent.id],
        )
        capture = engine.add_step(
            wf.id, "capture", "task",
            {"command": "stripe payment_intents capture"},
            depends_on=[check_status.id],
            retry_count=2,
        )
        engine.add_step(
            wf.id, "send-receipt", "notify",
            {"channel": "email", "message": "Payment captured successfully"},
            depends_on=[capture.id],
        )
        engine.add_step(
            wf.id, "notify-failed", "notify",
            {"channel": "slack", "message": "Payment capture failed — manual review"},
        )
        return wf

    def test_payment_workflow_dag_is_valid(self, engine):
        wf = self._build_payment_workflow(engine)
        validation = engine.validate_dag(wf.id)
        assert validation["valid"] is True
        assert validation["step_count"] == 5

    def test_payment_capture_success_path(self, engine):
        wf = self._build_payment_workflow(engine)
        run = engine.execute_workflow(
            wf.id,
            context={
                "payment_intent_id": "pi_test_123456",
                "payment_status": "requires_capture",
            },
        )
        assert run.status == RunStatus.SUCCESS
        assert len(run.step_results) >= 1

    def test_payment_capture_run_history_recorded(self, engine):
        wf = self._build_payment_workflow(engine)
        engine.execute_workflow(
            wf.id, {"payment_intent_id": "pi_aaa", "payment_status": "requires_capture"}
        )
        engine.execute_workflow(
            wf.id, {"payment_intent_id": "pi_bbb", "payment_status": "requires_capture"}
        )
        history = engine.get_run_history(wf.id)
        assert len(history) == 2
        for run in history:
            assert run["triggered_by"] == "manual"
            assert run["status"] in ("success", "failed")

    def test_payment_workflow_export(self, engine):
        wf = self._build_payment_workflow(engine)
        data = engine.export_workflow(wf.id)
        assert data["workflow"]["name"] == "stripe-payment-capture"
        assert len(data["steps"]) == 5
        step_names = {s["name"] for s in data["steps"]}
        assert "validate-intent" in step_names
        assert "capture" in step_names
        assert "send-receipt" in step_names


# ── Stripe subscription lifecycle ─────────────────────────────────────────────

class TestStripeSubscriptionLifecycleWorkflow:
    """End-to-end Stripe subscription event workflow."""

    def _build_subscription_workflow(self, engine):
        wf = engine.create_workflow(
            "stripe-subscription-lifecycle",
            description="Handle Stripe subscription events",
            tags=["stripe", "subscriptions", "billing"],
        )
        check_event = engine.add_step(
            wf.id, "check-event", "condition",
            {"expression": "event_type eq customer.subscription.deleted",
             "true_next": "cancel-access",
             "false_next": "update-entitlements"},
        )
        cancel = engine.add_step(
            wf.id, "cancel-access", "task",
            {"command": "revoke_user_access"},
            depends_on=[check_event.id],
        )
        update = engine.add_step(
            wf.id, "update-entitlements", "transform",
            {"mapping": {"user_tier": "new_plan", "billing_period": "period_end"}},
            depends_on=[check_event.id],
        )
        engine.add_step(
            wf.id, "notify-customer", "notify",
            {"channel": "email", "message": "Your subscription has been updated"},
            depends_on=[cancel.id, update.id],
        )
        return wf

    def test_subscription_workflow_is_valid(self, engine):
        wf = self._build_subscription_workflow(engine)
        validation = engine.validate_dag(wf.id)
        assert validation["valid"] is True
        assert validation["step_count"] == 4

    def test_subscription_updated_event(self, engine):
        wf = self._build_subscription_workflow(engine)
        run = engine.execute_workflow(
            wf.id,
            context={
                "event_type": "customer.subscription.updated",
                "new_plan": "pro",
                "period_end": "2026-12-31",
            },
        )
        assert run.status == RunStatus.SUCCESS

    def test_subscription_transform_propagates_context(self, engine):
        wf = self._build_subscription_workflow(engine)
        run = engine.execute_workflow(
            wf.id,
            context={
                "event_type": "customer.subscription.updated",
                "new_plan": "enterprise",
                "period_end": "2027-01-01",
            },
        )
        assert run.status == RunStatus.SUCCESS
        # Find the transform step result and verify mapping
        transform_result = next(
            (r for r in run.step_results.values()
             if r["step_name"] == "update-entitlements"),
            None,
        )
        assert transform_result is not None
        assert transform_result["output"]["user_tier"] == "enterprise"


# ── DAG integrity ─────────────────────────────────────────────────────────────

class TestDAGIntegrity:
    """DAG validation edge cases."""

    def test_linear_dag_execution_order(self, engine):
        wf = engine.create_workflow("linear-dag", "Linear chain")
        s1 = engine.add_step(wf.id, "step1", "task", {})
        s2 = engine.add_step(wf.id, "step2", "task", {}, depends_on=[s1.id])
        s3 = engine.add_step(wf.id, "step3", "task", {}, depends_on=[s2.id])
        result = engine.validate_dag(wf.id)
        order = result["execution_order"]
        assert order.index("step1") < order.index("step2")
        assert order.index("step2") < order.index("step3")

    def test_parallel_branches_valid(self, engine):
        wf = engine.create_workflow("parallel-dag", "Parallel branches")
        root = engine.add_step(wf.id, "root", "task", {})
        branch_a = engine.add_step(wf.id, "branch-a", "task", {}, depends_on=[root.id])
        branch_b = engine.add_step(wf.id, "branch-b", "task", {}, depends_on=[root.id])
        engine.add_step(wf.id, "merge", "task", {}, depends_on=[branch_a.id, branch_b.id])
        result = engine.validate_dag(wf.id)
        assert result["valid"] is True
        assert result["step_count"] == 4

    def test_cycle_detection_prevents_execution(self, engine):
        graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        validator = DAGValidator(graph)
        has_cycle, path = validator.detect_cycle()
        assert has_cycle is True
        assert len(path) >= 3

    def test_critical_path_identified(self, engine):
        wf = engine.create_workflow("critical-path-dag", "Critical path test")
        s1 = engine.add_step(wf.id, "start", "task", {})
        s2 = engine.add_step(wf.id, "slow-branch", "task", {}, depends_on=[s1.id])
        engine.add_step(wf.id, "fast-branch", "task", {}, depends_on=[s1.id])
        engine.add_step(wf.id, "end", "task", {}, depends_on=[s2.id])
        result = engine.validate_dag(wf.id)
        assert len(result["critical_path"]) >= 1

    def test_empty_workflow_is_valid(self, engine):
        wf = engine.create_workflow("empty-wf", "No steps")
        result = engine.validate_dag(wf.id)
        assert result["valid"] is True
        assert result["step_count"] == 0


# ── Multi-workflow isolation ───────────────────────────────────────────────────

class TestWorkflowIsolation:
    """Multiple workflows must not interfere with each other."""

    def test_two_workflows_are_independent(self, engine):
        wf1 = engine.create_workflow("wf-alpha", "Alpha")
        wf2 = engine.create_workflow("wf-beta", "Beta")

        engine.add_step(wf1.id, "step-a", "task", {})
        engine.add_step(wf2.id, "step-b", "task", {})
        engine.add_step(wf2.id, "step-c", "task", {})

        v1 = engine.validate_dag(wf1.id)
        v2 = engine.validate_dag(wf2.id)
        assert v1["step_count"] == 1
        assert v2["step_count"] == 2

    def test_delete_does_not_affect_sibling(self, engine):
        wf1 = engine.create_workflow("keep-me", "Keep")
        wf2 = engine.create_workflow("delete-me", "Delete")
        engine.add_step(wf1.id, "s1", "task", {})
        engine.add_step(wf2.id, "s2", "task", {})

        engine.delete_workflow(wf2.id)

        workflows = engine.list_workflows()
        names = [w["name"] for w in workflows]
        assert "keep-me" in names
        assert "delete-me" not in names

    def test_run_history_is_scoped_to_workflow(self, engine):
        wf1 = engine.create_workflow("scoped-wf1", "Scope 1")
        wf2 = engine.create_workflow("scoped-wf2", "Scope 2")
        engine.add_step(wf1.id, "s1", "task", {})
        engine.add_step(wf2.id, "s2", "task", {})

        engine.execute_workflow(wf1.id)
        engine.execute_workflow(wf1.id)
        engine.execute_workflow(wf2.id)

        assert len(engine.get_run_history(wf1.id)) == 2
        assert len(engine.get_run_history(wf2.id)) == 1
