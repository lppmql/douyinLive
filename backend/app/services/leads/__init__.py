"""外部客资接入服务。"""

from app.services.leads.kezi_sync import kezi_lead_sync_manager, sync_kezi_leads

__all__ = ["kezi_lead_sync_manager", "sync_kezi_leads"]
