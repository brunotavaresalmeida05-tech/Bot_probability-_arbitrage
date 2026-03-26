"""
ML Price Predictor
Random Forest para prever direção do preço.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import pickle
import os


class PricePredictor:
    def __init__(self, model_path='models/rf_predictor.pkl'):
        self.model_path = model_path
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False

        # Carregar modelo se existir
        if os.path.exists(model_path):
            self.load_model()

    def engineer_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Cria 20+ features para ML.

        Features:
        - Price momentum (5, 10, 20 períodos)
        - Volume ratios
        - Volatility metrics
        - RSI, MACD, Stochastic
        - ATR ratios
        - Support/Resistance proximity
        """
        features = []

        # Momentum features
        for period in [5, 10, 20]:
            prev = df['close'].shift(period).iloc[-1]
            if prev and prev > 0:
                momentum = (df['close'].iloc[-1] - prev) / prev
            else:
                momentum = 0.0
            features.append(momentum)

        # Volume features
        vol_mean = df['volume'].iloc[-20:-1].mean()
        vol_ratio = df['volume'].iloc[-1] / vol_mean if vol_mean > 0 else 1.0
        features.append(vol_ratio)

        # Volatility
        returns = df['close'].pct_change()
        vol_5 = returns.iloc[-5:].std()
        vol_20 = returns.iloc[-20:].std()
        features.extend([
            vol_5 if not np.isnan(vol_5) else 0,
            vol_20 if not np.isnan(vol_20) else 0,
            vol_5 / vol_20 if vol_20 > 0 else 1.0,
        ])

        # RSI
        rsi = self._calculate_rsi(df['close'], 14)
        features.append(rsi if not np.isnan(rsi) else 50.0)

        # MACD
        macd, signal = self._calculate_macd(df['close'])
        macd = macd if not np.isnan(macd) else 0.0
        signal = signal if not np.isnan(signal) else 0.0
        features.extend([macd, signal, macd - signal])

        # ATR ratio
        atr = df['atr'].iloc[-1] if 'atr' in df.columns else 0
        close_last = df['close'].iloc[-1]
        atr_ratio = atr / close_last if close_last > 0 else 0
        features.append(atr_ratio)

        # Distance from MA
        ma_20 = df['close'].iloc[-20:].mean()
        dist_ma = (close_last - ma_20) / ma_20 if ma_20 > 0 else 0
        features.append(dist_ma)

        # Stochastic
        stoch_k = self._calculate_stochastic(df)
        features.append(stoch_k)

        # Support/Resistance proximity
        high_20 = df['high'].iloc[-20:].max()
        low_20 = df['low'].iloc[-20:].min()
        dist_high = (high_20 - close_last) / high_20 if high_20 > 0 else 0
        dist_low = (close_last - low_20) / low_20 if low_20 > 0 else 0
        features.extend([dist_high, dist_low])

        # Trend strength (linear regression slope)
        close_prices = df['close'].values[-20:]
        x = np.arange(len(close_prices))
        slope = np.polyfit(x, close_prices, 1)[0]
        features.append(slope)

        # Substituir NaN/Inf residuais
        features = [0.0 if (np.isnan(f) or np.isinf(f)) else float(f)
                    for f in features]

        return np.array(features).reshape(1, -1)

    def _calculate_rsi(self, prices, period=14):
        """RSI indicator."""
        deltas = prices.diff()
        gain = deltas.where(deltas > 0, 0).rolling(window=period).mean()
        loss = -deltas.where(deltas < 0, 0).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])

    def _calculate_macd(self, prices):
        """MACD indicator."""
        ema_12 = prices.ewm(span=12).mean()
        ema_26 = prices.ewm(span=26).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9).mean()
        return float(macd.iloc[-1]), float(signal.iloc[-1])

    def _calculate_stochastic(self, df, period=14):
        """Stochastic oscillator."""
        low_min = df['low'].iloc[-period:].min()
        high_max = df['high'].iloc[-period:].max()

        if high_max == low_min:
            return 50.0

        stoch_k = ((df['close'].iloc[-1] - low_min) /
                   (high_max - low_min)) * 100
        return float(stoch_k)

    def train(self, historical_data: list) -> dict:
        """
        Treina modelo com dados históricos.

        Args:
            historical_data: [{'df': DataFrame, 'label': 1/-1/0}, ...]
                            1 = UP, -1 = DOWN, 0 = NEUTRAL
        """
        X = []
        y = []

        for data in historical_data:
            try:
                features = self.engineer_features(data['df'])
                X.append(features[0])
                y.append(data['label'])
            except Exception:
                continue

        if len(X) < 50:
            return {'accuracy': 0, 'n_samples': len(X),
                    'error': 'Insufficient data (need 50+)'}

        X = np.array(X)
        y = np.array(y)

        # Normalizar
        X_scaled = self.scaler.fit_transform(X)

        # Treinar Random Forest
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=20,
            random_state=42,
        )

        self.model.fit(X_scaled, y)
        self.is_trained = True

        # Salvar modelo
        self.save_model()

        return {
            'accuracy': float(self.model.score(X_scaled, y)),
            'n_samples': len(y),
        }

    def predict(self, df: pd.DataFrame) -> dict:
        """
        Prediz próximo movimento.

        Returns: {
            'direction': 1/-1/0,
            'confidence': float (0-1),
            'proba_up': float,
            'proba_down': float,
            'proba_neutral': float,
        }
        """
        if not self.is_trained:
            return {
                'direction': 0,
                'confidence': 0.0,
                'proba_up': 0.33,
                'proba_down': 0.33,
                'proba_neutral': 0.34,
            }

        try:
            features = self.engineer_features(df)
            features_scaled = self.scaler.transform(features)

            # Predição
            prediction = self.model.predict(features_scaled)[0]
            probas = self.model.predict_proba(features_scaled)[0]

            # Probabilidades por classe
            class_mapping = {c: i for i, c in enumerate(self.model.classes_)}

            proba_down = float(probas[class_mapping[-1]]) if -1 in class_mapping else 0.0
            proba_neutral = float(probas[class_mapping[0]]) if 0 in class_mapping else 0.0
            proba_up = float(probas[class_mapping[1]]) if 1 in class_mapping else 0.0

            confidence = float(max(probas))

            return {
                'direction': int(prediction),
                'confidence': confidence,
                'proba_up': proba_up,
                'proba_down': proba_down,
                'proba_neutral': proba_neutral,
            }
        except Exception as e:
            print(f"ML predict error: {e}")
            return {
                'direction': 0,
                'confidence': 0.0,
                'proba_up': 0.33,
                'proba_down': 0.33,
                'proba_neutral': 0.34,
            }

    def get_feature_importance(self) -> dict:
        """Retorna importância de cada feature."""
        if not self.is_trained:
            return {}

        feature_names = [
            'momentum_5', 'momentum_10', 'momentum_20',
            'volume_ratio',
            'volatility_5', 'volatility_20', 'vol_ratio',
            'rsi_14',
            'macd', 'macd_signal', 'macd_hist',
            'atr_ratio',
            'dist_ma_20',
            'stochastic_k',
            'dist_high_20', 'dist_low_20',
            'trend_slope',
        ]

        importances = self.model.feature_importances_
        result = {}
        for i, name in enumerate(feature_names):
            if i < len(importances):
                result[name] = float(importances[i])

        # Ordenar por importância
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))

    def save_model(self):
        """Salva modelo treinado."""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

        with open(self.model_path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'scaler': self.scaler,
            }, f)

    def load_model(self) -> bool:
        """Carrega modelo salvo."""
        try:
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)
                self.model = data['model']
                self.scaler = data['scaler']
                self.is_trained = True
            return True
        except Exception:
            return False
