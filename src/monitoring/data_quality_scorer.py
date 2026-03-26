"""
Data Quality Scorer
Avalia qualidade e confiabilidade de dados de múltiplas fontes
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List

class DataQualityScorer:
    def __init__(self, api_aggregator, health_monitor):
        self.api_agg = api_aggregator
        self.health = health_monitor
        self.quality_history = []
    
    def calculate_quality_score(self, symbol: str) -> Dict:
        """
        Score de qualidade de dados (0-100).
        
        Componentes:
        - API availability (30%)
        - Price consensus (25%)
        - Data freshness (20%)
        - News coverage (15%)
        - Volume reliability (10%)
        """
        scores = {}
        
        # 1. API Availability (30 pontos)
        api_score = self._score_api_availability()
        scores['api_availability'] = api_score * 0.30
        
        # 2. Price Consensus (25 pontos)
        consensus_score = self._score_price_consensus(symbol)
        scores['price_consensus'] = consensus_score * 0.25
        
        # 3. Data Freshness (20 pontos)
        freshness_score = self._score_data_freshness(symbol)
        scores['data_freshness'] = freshness_score * 0.20
        
        # 4. News Coverage (15 pontos)
        news_score = self._score_news_coverage(symbol)
        scores['news_coverage'] = news_score * 0.15
        
        # 5. Volume Reliability (10 pontos)
        volume_score = self._score_volume_reliability(symbol)
        scores['volume_reliability'] = volume_score * 0.10
        
        # Total score
        total_score = sum(scores.values())
        
        # Grade
        grade = self._score_to_grade(total_score)
        
        result = {
            'total_score': total_score,
            'grade': grade,
            'components': scores,
            'recommendation': self._get_recommendation(total_score),
            'timestamp': datetime.now()
        }
        
        # Log
        self.quality_history.append(result)
        
        return result
    
    def _score_api_availability(self) -> float:
        """
        Score baseado em quantas APIs estão healthy.
        
        Returns: 0-100
        """
        health = self.health.check_all_sources()
        
        total = health['healthy'] + health['degraded'] + health['down']
        if total == 0:
            return 0
        
        # Healthy = 100%, Degraded = 50%, Down = 0%
        weighted = (
            (health['healthy'] * 100) +
            (health['degraded'] * 50) +
            (health['down'] * 0)
        ) / total
        
        return weighted
    
    def _score_price_consensus(self, symbol: str) -> float:
        """
        Score baseado em agreement entre fontes de preço.
        
        Returns: 0-100
        """
        consensus = self.api_agg.get_consensus_price(symbol)
        
        if not consensus or consensus['price'] is None:
            return 0
        
        # Confidence já é 0-1
        confidence = consensus['confidence']
        
        # Sources count (mais fontes = melhor)
        sources_bonus = min(consensus['sources_count'] * 10, 20)
        
        # Agreement level
        if consensus.get('agreement_level') == 'STRONG':
            agreement_bonus = 20
        elif consensus.get('agreement_level') == 'GOOD':
            agreement_bonus = 10
        else:
            agreement_bonus = 0
        
        score = (confidence * 60) + sources_bonus + agreement_bonus
        
        return min(100, score)
    
    def _score_data_freshness(self, symbol: str) -> float:
        """
        Score baseado em quão recentes são os dados.
        
        Returns: 0-100
        """
        # Check cache age
        cache_key = f"price_{symbol}"
        
        if cache_key not in self.api_agg.cache:
            return 0
        
        cache_entry = self.api_agg.cache[cache_key]
        age_seconds = (datetime.now() - cache_entry['timestamp']).seconds
        
        # Freshness score
        # < 30s = 100
        # < 60s = 80
        # < 120s = 60
        # > 120s = diminui
        
        if age_seconds < 30:
            return 100
        elif age_seconds < 60:
            return 80
        elif age_seconds < 120:
            return 60
        else:
            # Decay
            return max(0, 60 - ((age_seconds - 120) / 10))
    
    def _score_news_coverage(self, symbol: str) -> float:
        """
        Score baseado em cobertura de notícias.
        
        Returns: 0-100
        """
        sentiment = self.api_agg.get_news_sentiment(symbol)
        
        if not sentiment:
            return 0
        
        # Sources count (mais fontes = melhor)
        sources_score = min(sentiment['sources_count'] * 15, 60)
        
        # Confidence
        confidence_score = sentiment['confidence'] * 40
        
        return sources_score + confidence_score
    
    def _score_volume_reliability(self, symbol: str) -> float:
        """
        Score baseado em confiabilidade do volume.
        
        Returns: 0-100
        """
        vol_data = self.api_agg.get_real_volume(symbol)
        
        if not vol_data or vol_data['total_volume'] == 0:
            return 0
        
        # Sources count
        sources_count = len(vol_data.get('sources', []))
        
        if sources_count == 0:
            return 0
        elif sources_count == 1:
            return 50
        elif sources_count == 2:
            return 75
        else:
            return 100
    
    def _score_to_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        if score >= 90:
            return 'A+'
        elif score >= 85:
            return 'A'
        elif score >= 80:
            return 'A-'
        elif score >= 75:
            return 'B+'
        elif score >= 70:
            return 'B'
        elif score >= 65:
            return 'B-'
        elif score >= 60:
            return 'C+'
        elif score >= 55:
            return 'C'
        elif score >= 50:
            return 'C-'
        else:
            return 'F'
    
    def _get_recommendation(self, score: float) -> str:
        """Trading recommendation baseado em quality score."""
        if score >= 85:
            return 'EXCELLENT - Safe to trade with full confidence'
        elif score >= 70:
            return 'GOOD - Trade normally'
        elif score >= 60:
            return 'ACCEPTABLE - Reduce position size by 25%'
        elif score >= 50:
            return 'POOR - Reduce position size by 50%'
        else:
            return 'CRITICAL - Do not trade this symbol'
    
    def get_quality_report(self, symbols: List[str]) -> pd.DataFrame:
        """
        Relatório de qualidade para múltiplos símbolos.
        """
        reports = []
        
        for symbol in symbols:
            score = self.calculate_quality_score(symbol)
            
            reports.append({
                'Symbol': symbol,
                'Score': score['total_score'],
                'Grade': score['grade'],
                'API': score['components']['api_availability'] / 0.30,
                'Consensus': score['components']['price_consensus'] / 0.25,
                'Freshness': score['components']['data_freshness'] / 0.20,
                'News': score['components']['news_coverage'] / 0.15,
                'Volume': score['components']['volume_reliability'] / 0.10,
                'Recommendation': score['recommendation']
            })
        
        df = pd.DataFrame(reports)
        df = df.sort_values('Score', ascending=False)
        
        return df
    
    def get_overall_system_health(self) -> Dict:
        """
        Health geral do sistema de dados.
        """
        # APIs health
        api_health = self.health.check_all_sources()
        
        # Average uptime (last 24h)
        uptime_report = self.health.get_uptime_report(hours=24)
        
        if not uptime_report.empty:
            avg_uptime = uptime_report['Uptime %'].mean()
        else:
            avg_uptime = 0
        
        # Quality scores history
        if self.quality_history:
            recent = [q for q in self.quality_history 
                     if q['timestamp'] > datetime.now() - timedelta(hours=1)]
            
            if recent:
                avg_score = np.mean([q['total_score'] for q in recent])
            else:
                avg_score = 0
        else:
            avg_score = 0
        
        # Overall health score
        total_sources = api_health['healthy'] + api_health['down']
        health_score = (
            ((api_health['healthy'] / total_sources) * 40 if total_sources > 0 else 0) +
            (avg_uptime * 0.30) +
            (avg_score * 0.30)
        )
        
        return {
            'overall_score': health_score,
            'grade': self._score_to_grade(health_score),
            'apis_healthy': api_health['healthy'],
            'apis_down': api_health['down'],
            'avg_uptime_24h': avg_uptime,
            'avg_quality_score': avg_score,
            'status': 'HEALTHY' if health_score >= 80 else
                     'DEGRADED' if health_score >= 60 else
                     'CRITICAL'
        }
