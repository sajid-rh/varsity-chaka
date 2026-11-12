"""add ride offers, requests, trips, blocks and contact disclosures

Revision ID: c4b1897e01d2
Revises: 375beac71606
Create Date: 2026-11-12 21:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'c4b1897e01d2'
down_revision: Union[str, None] = '375beac71606'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. ride_offers
    op.create_table(
        'ride_offers',
        sa.Column('id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('university_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('rider_profile_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('rider_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('origin_lat', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('origin_lng', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('origin_label', sa.String(length=150), nullable=False),
        sa.Column('dest_lat', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('dest_lng', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('dest_label', sa.String(length=150), nullable=False),
        sa.Column('direction', sa.Enum('to_campus', 'from_campus', name='offer_direction'), nullable=False),
        sa.Column('departure_time', sa.DateTime(), nullable=False),
        sa.Column('route_distance_m', sa.Integer(), nullable=True),
        sa.Column('route_duration_s', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('open', 'booked', 'closed', 'cancelled', name='offer_status'), server_default=sa.text("'open'"), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['rider_id'], ['users.id'], name=op.f('fk_ride_offers_rider_id_users')),
        sa.ForeignKeyConstraint(['rider_profile_id'], ['rider_profiles.id'], name=op.f('fk_ride_offers_rider_profile_id_rider_profiles')),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('fk_ride_offers_university_id_universities')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ride_offers'))
    )
    op.create_index(op.f('ix_ride_offers_university_id'), 'ride_offers', ['university_id'], unique=False)
    op.create_index(op.f('ix_ride_offers_rider_profile_id'), 'ride_offers', ['rider_profile_id'], unique=False)
    op.create_index(op.f('ix_ride_offers_rider_id'), 'ride_offers', ['rider_id'], unique=False)
    op.create_index('ix_ride_offers_search', 'ride_offers', ['university_id', 'status', 'departure_time'], unique=False)

    # 2. ride_requests
    op.create_table(
        'ride_requests',
        sa.Column('id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('university_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('passenger_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('pickup_lat', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('pickup_lng', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('pickup_label', sa.String(length=150), nullable=False),
        sa.Column('dest_lat', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('dest_lng', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('dest_label', sa.String(length=150), nullable=False),
        sa.Column('preferred_time', sa.DateTime(), nullable=False),
        sa.Column('status', sa.Enum('open', 'matched', 'cancelled', 'expired', name='request_status'), server_default=sa.text("'open'"), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['passenger_id'], ['users.id'], name=op.f('fk_ride_requests_passenger_id_users')),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('fk_ride_requests_university_id_universities')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ride_requests'))
    )
    op.create_index(op.f('ix_ride_requests_university_id'), 'ride_requests', ['university_id'], unique=False)
    op.create_index(op.f('ix_ride_requests_passenger_id'), 'ride_requests', ['passenger_id'], unique=False)
    op.create_index('ix_ride_requests_search', 'ride_requests', ['university_id', 'status', 'preferred_time'], unique=False)

    # 3. trips
    op.create_table(
        'trips',
        sa.Column('id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('university_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('ride_offer_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('ride_request_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=True),
        sa.Column('rider_profile_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('rider_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('passenger_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('status', sa.Enum('requested', 'accepted', 'confirmed', 'in_progress', 'completed', 'cancelled', name='trip_status'), server_default=sa.text("'requested'"), nullable=False),
        sa.Column('active_offer_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=True),
        sa.Column('match_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('match_explanation', sa.String(length=500), nullable=True),
        sa.Column('suggested_fare_min', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('suggested_fare_max', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('helmet_confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_by', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=True),
        sa.Column('cancellation_reason', sa.String(length=255), nullable=True),
        sa.Column('rider_confirmed_complete_at', sa.DateTime(), nullable=True),
        sa.Column('passenger_confirmed_complete_at', sa.DateTime(), nullable=True),
        sa.Column('disputed', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('dispute_reason', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['active_offer_id'], ['ride_offers.id'], ondelete='SET NULL', name=op.f('fk_trips_active_offer_id_ride_offers')),
        sa.ForeignKeyConstraint(['cancelled_by'], ['users.id'], name=op.f('fk_trips_cancelled_by_users')),
        sa.ForeignKeyConstraint(['passenger_id'], ['users.id'], name=op.f('fk_trips_passenger_id_users')),
        sa.ForeignKeyConstraint(['ride_offer_id'], ['ride_offers.id'], name=op.f('fk_trips_ride_offer_id_ride_offers')),
        sa.ForeignKeyConstraint(['ride_request_id'], ['ride_requests.id'], name=op.f('fk_trips_ride_request_id_ride_requests')),
        sa.ForeignKeyConstraint(['rider_id'], ['users.id'], name=op.f('fk_trips_rider_id_users')),
        sa.ForeignKeyConstraint(['rider_profile_id'], ['rider_profiles.id'], name=op.f('fk_trips_rider_profile_id_rider_profiles')),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('fk_trips_university_id_universities')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_trips')),
        sa.UniqueConstraint('active_offer_id', name=op.f('uq_trips_active_offer_id'))
    )
    op.create_index(op.f('ix_trips_university_id'), 'trips', ['university_id'], unique=False)
    op.create_index(op.f('ix_trips_ride_offer_id'), 'trips', ['ride_offer_id'], unique=False)
    op.create_index(op.f('ix_trips_ride_request_id'), 'trips', ['ride_request_id'], unique=False)
    op.create_index(op.f('ix_trips_rider_profile_id'), 'trips', ['rider_profile_id'], unique=False)
    op.create_index(op.f('ix_trips_rider_id'), 'trips', ['rider_id'], unique=False)
    op.create_index(op.f('ix_trips_passenger_id'), 'trips', ['passenger_id'], unique=False)
    op.create_index('ix_trips_uni_status', 'trips', ['university_id', 'status'], unique=False)
    op.create_index('ix_trips_rider_status', 'trips', ['rider_id', 'status'], unique=False)
    op.create_index('ix_trips_passenger_status', 'trips', ['passenger_id', 'status'], unique=False)

    # 4. blocks
    op.create_table(
        'blocks',
        sa.Column('id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('university_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('blocker_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('blocked_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['blocked_id'], ['users.id'], name=op.f('fk_blocks_blocked_id_users')),
        sa.ForeignKeyConstraint(['blocker_id'], ['users.id'], name=op.f('fk_blocks_blocker_id_users')),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('fk_blocks_university_id_universities')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_blocks')),
        sa.UniqueConstraint('blocker_id', 'blocked_id', name='uq_block_pair')
    )
    op.create_index(op.f('ix_blocks_university_id'), 'blocks', ['university_id'], unique=False)
    op.create_index(op.f('ix_blocks_blocker_id'), 'blocks', ['blocker_id'], unique=False)
    op.create_index(op.f('ix_blocks_blocked_id'), 'blocks', ['blocked_id'], unique=False)

    # 5. contact_disclosures
    op.create_table(
        'contact_disclosures',
        sa.Column('id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('university_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('trip_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('viewer_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('disclosed_user_id', sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), 'mysql').with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['disclosed_user_id'], ['users.id'], name=op.f('fk_contact_disclosures_disclosed_user_id_users')),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], name=op.f('fk_contact_disclosures_trip_id_trips')),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('fk_contact_disclosures_university_id_universities')),
        sa.ForeignKeyConstraint(['viewer_id'], ['users.id'], name=op.f('fk_contact_disclosures_viewer_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_contact_disclosures'))
    )
    op.create_index(op.f('ix_contact_disclosures_university_id'), 'contact_disclosures', ['university_id'], unique=False)
    op.create_index('ix_contact_disclosures_trip', 'contact_disclosures', ['trip_id'], unique=False)


def downgrade() -> None:
    op.drop_table('contact_disclosures')
    op.drop_table('blocks')
    op.drop_table('trips')
    op.drop_table('ride_requests')
    op.drop_table('ride_offers')
