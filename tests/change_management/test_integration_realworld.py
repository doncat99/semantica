"""Integration coverage for the independent ontology change-control owner."""

import pytest

from semantica.change_management import OntologyVersionManager


class TestFinancialCompliance:
    """Test financial compliance scenarios (SOX § 404)"""
    
    
    def test_sox_change_control(self):
        """Test SOX-compliant change control process"""
        manager = OntologyVersionManager()
        
        # Financial ontology
        financial_ontology = {
            "uri": "https://bank.com/ontology/financial",
            "version_info": {"version": "1.0", "date": "2024-01-30"},
            "structure": {
                "classes": ["Account", "Transaction", "Customer"],
                "properties": ["accountNumber", "balance", "transactionAmount"],
                "individuals": ["CheckingAccount", "SavingsAccount"],
                "axioms": [
                    "Account belongsTo exactly 1 Customer",
                    "Transaction involves exactly 1 Account"
                ]
            }
        }
        
        # Initial version
        v1 = manager.create_snapshot(
            financial_ontology,
            "financial_ont_v1.0",
            "architect@bank.com",
            "Initial financial ontology"
        )
        
        # Add compliance requirements
        financial_ontology["structure"]["classes"].extend(["ComplianceCheck", "AuditLog"])
        financial_ontology["structure"]["properties"].extend(["complianceStatus", "auditTimestamp"])
        financial_ontology["structure"]["axioms"].append(
            "Transaction requiresCompliance exactly 1 ComplianceCheck"
        )
        
        v2 = manager.create_snapshot(
            financial_ontology,
            "financial_ont_v2.0",
            "compliance@bank.com",
            "Added SOX compliance requirements"
        )
        
        # Verify structural changes are tracked
        diff = manager.compare_versions("financial_ont_v1.0", "financial_ont_v2.0")
        assert "ComplianceCheck" in diff["classes_added"]
        assert "AuditLog" in diff["classes_added"]
        assert len(diff["axioms_added"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
