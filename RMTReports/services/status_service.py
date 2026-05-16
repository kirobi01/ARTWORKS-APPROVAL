import logging
from ..config.notification_config import STATUS_FLOW

logger = logging.getLogger(__name__)

class RMTRStatusManager:
    @staticmethod
    def get_next_status(current_status, approved=True):
        logger.info(f"Getting next status for current_status: {current_status}, approved: {approved}")
        
        if not approved:
            logger.info("Request rejected, returning 'rejected' status")
            return 'rejected'
            
        next_status = STATUS_FLOW.get(current_status, current_status)
        logger.info(f"Next status determined: {next_status}")
        return next_status

    @staticmethod
    def get_next_stage(current_stage):
        stage_order = [
            'HODPurchaseApproval',
            'ManagementApproval',
            'FMApproval',
            'HODApproval',
            'TestResults',
            'QAOApproval',
            'HODTestApproval',
            'FMTestApproval',
            'ManagementTestApproval',
            'MilanApproval'
        ]
        
        try:
            current_index = stage_order.index(current_stage)
            if current_index < len(stage_order) - 1:
                return stage_order[current_index + 1]
            return None
        except ValueError:
            return None